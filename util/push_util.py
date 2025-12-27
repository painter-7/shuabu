import json
import re
import requests
from datetime import datetime
import pytz


def get_beijing_time():
    """获取北京时间"""
    target_timezone = pytz.timezone('Asia/Shanghai')
    return datetime.now().astimezone(target_timezone)


def format_now():
    """格式化当前时间"""
    return get_beijing_time().strftime("%Y-%m-%d %H:%M:%S")


def format_date_hm():
    """格式化日期和时分秒"""
    bj_time = get_beijing_time()
    date = bj_time.strftime("%Y-%m-%d")
    hm = bj_time.strftime("%H:%M:%S")
    return date, hm


class PushConfig:
    """推送配置类"""

    def __init__(self,
                 push_plus_token=None,
                 push_plus_hour=None,
                 push_plus_max=30,
                 push_wechat_webhook_key=None,
                 telegram_bot_token=None,
                 telegram_chat_id=None):
        self.push_plus_token = push_plus_token
        self.push_plus_hour = push_plus_hour
        self.push_plus_max = int(push_plus_max) if push_plus_max else 30
        self.push_wechat_webhook_key = push_wechat_webhook_key
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id


def push_plus(token, title, content):
    """推送到PushPlus"""
    requestUrl = f"http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
        "channel": "wechat"
    }
    try:
        response = requests.post(requestUrl, data=data)
        if response.status_code == 200:
            json_res = response.json()
            print(f"pushplus推送完毕：{json_res['code']}-{json_res['msg']}")
        else:
            print("pushplus推送失败")
    except requests.exceptions.RequestException as e:
        print(f"pushplus推送网络异常: {e}")
    except Exception as e:
        print(f"pushplus推送未知异常: {e}")


def push_wechat_webhook(key, title, content):
    """推送到企业微信"""
    requestUrl = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    payload = {
        "msgtype": "markdown_v2",
        "markdown_v2": {
            "content": buildWeChatContent(title, content)
        }
    }
    try:
        response = requests.post(requestUrl, json=payload)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('errcode') == 0:
                print(f"企业微信推送完毕：{json_res['errmsg']}")
            else:
                print(f"企业微信推送失败：{json_res.get('errmsg', '未知错误')}")
        else:
            print("企业微信推送失败")
    except requests.exceptions.RequestException as e:
        print(f"企业微信推送异常: {e}")
    except Exception as e:
        print(f"企业微信推送发生未知异常: {e}")


def buildWeChatContent(title, content) -> str:
    return f"""# {title}\n{content}"""


def push_telegram_bot(bot_token, chat_id, content):
    """推送到Telegram"""
    requestUrl = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": int(chat_id),
        "text": content,
        "parse_mode": "HTML"
    }
    print(f"post to url: {requestUrl}")
    print(f"payload: {json.dumps(payload)}")
    try:
        response = requests.post(requestUrl, json=payload)
        if response.status_code == 200:
            json_res = response.json()
            if json_res.get('ok') is True:
                print(f"telegram bot推送完毕：{json_res['result']['message_id']}")
            else:
                print(f"telegram bot推送失败: {json.dumps(json_res)}")
        else:
            print(f"telegram bot推送失败: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"telegram bot推送异常: {e}")
    except Exception as e:
        print(f"telegram bot推送发生未知异常: {e}")


def push_results(exec_results, summary, config: PushConfig):
    """推送所有结果"""
    if not_in_push_time_range(config):
        return
    push_to_push_plus(exec_results, summary, config)
    push_to_wechat_webhook(exec_results, summary, config)
    push_to_telegram_bot(exec_results, summary, config)


def not_in_push_time_range(config: PushConfig) -> bool:
    """检查是否在推送时间范围内"""
    if not config.push_plus_hour:
        return False
    time_bj = get_beijing_time()
    if config.push_plus_hour.isdigit():
        if time_bj.hour == int(config.push_plus_hour):
            print(f"当前设置推送整点为：{config.push_plus_hour}, 当前整点为：{time_bj.hour}，执行推送")
            return False
    try:
        with open('cron_change_time', 'r') as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1].strip()
                match = re.search(r'北京时间\(0?(\d+):\d+\)', last_line)
                if match:
                    cron_hour = int(match.group(1))
                    if int(config.push_plus_hour) == cron_hour:
                        print(f"当前设置推送整点为：{config.push_plus_hour}, 本次执行整点为：{cron_hour}，执行推送")
                        return False
    except Exception as e:
        print(f"读取cron_change_time文件出错: {e}")
    print(f"当前整点时间为：{time_bj}，不在配置的推送时间，不执行推送")
    return True


# ========== 公共函数1：账号脱敏 ==========
def desensitize_account(account):
    """账号脱敏：适配手机号、邮箱"""
    if not account:
        return "未知账号"
    if account.isdigit() and len(account) == 11:
        return f"{account[:3]}***{account[7:]}"
    elif "@" in account:
        user, domain = account.split("@", 1)
        user_safe = user[:3] + "***" if len(user) >= 3 else user[0] + "***"
        return f"{user_safe}@{domain}"
    else:
        return account[:3] + "***" if len(account) > 3 else account + "***"


# ========== 公共函数2：生成统一格式的推送内容 ==========
def generate_unified_content(exec_results, summary):
    """生成3种推送方式共用模板"""
    success_count = sum(1 for res in exec_results if res.get("success") is True)
    fail_count = len(exec_results) - success_count
    exec_date, finish_time = format_date_hm()
    step_range = re.search(r'(\d+-\d+)', summary).group(1) if re.search(r'(\d+-\d+)', summary) else "未知"
    content = f"""成功{success_count}个 失败{fail_count}个
{exec_date} 刷步报告 {finish_time}
====================
■ 执行日期：{exec_date}
■ 完成时间：{finish_time}
■ 步数范围：{step_range}
■ 同步结果：成功{success_count}个 | 失败{fail_count}个
■ 成功率：{(success_count/len(exec_results)*100):.1f}%
详细结果：
----------
"""
    for idx, exec_result in enumerate(exec_results, start=1):
        safe_user = desensitize_account(exec_result["user"])
        res_msg = exec_result["msg"]
        if exec_result.get("success") is True:
            content += f"{idx}. ✅ 成功 | 账号：{safe_user}\n返回：{res_msg}\n----------------\n"
        else:
            content += f"{idx}. ❌ 失败 | 账号：{safe_user}\n返回：{res_msg}\n----------------\n"
    return f"成功{success_count}个 失败{fail_count}个", content


# ========== 三种推送方式：统一调用公共生成函数 ==========
def push_to_push_plus(exec_results, summary, config: PushConfig):
    """推送到PushPlus"""
    if config.push_plus_token and config.push_plus_token != '' and config.push_plus_token != 'NO':
        push_title, push_content = generate_unified_content(exec_results, summary)
        push_plus(config.push_plus_token, push_title, push_content)
    else:
        print("未配置 PUSH_PLUS_TOKEN 跳过PUSHPLUS推送")


def push_to_wechat_webhook(exec_results, summary, config: PushConfig):
    """推送到企业微信"""
    if config.push_wechat_webhook_key and config.push_wechat_webhook_key != '' and config.push_wechat_webhook_key != 'NO':
        push_title, push_content = generate_unified_content(exec_results, summary)
        push_wechat_webhook(config.push_wechat_webhook_key, push_title, push_content)
    else:
        print("未配置 WECHAT_WEBHOOK_KEY 跳过微信推送")


def push_to_telegram_bot(exec_results, summary, config: PushConfig):
    """推送到Telegram"""
    if (config.telegram_bot_token and config.telegram_bot_token != '' and config.telegram_bot_token != 'NO' and
            config.telegram_chat_id and config.telegram_chat_id != ''):
        push_title, push_content = generate_unified_content(exec_results, summary)
        push_telegram_bot(config.telegram_bot_token, config.telegram_chat_id, push_content)
    else:
        print("未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 跳过telegram推送")