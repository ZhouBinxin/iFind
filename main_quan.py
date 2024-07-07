import zipfile
from datetime import datetime, timedelta

import pandas as pd
import requests
from sqlalchemy import create_engine, inspect
from tqdm import tqdm

from bondday import BondDay
from fileoperator import FileOperator
from dynaconf import Dynaconf
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
from environs import Env


def main():
    # 配置文件地址
    config_list = [

    ]

    # 配置文件目录
    src_dir = 'config_quan'

    file_list = os.listdir(src_dir)
    for file in file_list:
        if file.endswith('.yaml'):
            config_list.append(os.path.join(src_dir, file))

    # 错误监控
    send_error = False

    # 设置日期：上周五-本周五
    today = datetime.now()
    days_ahead = 4 - today.weekday()

    friday_date = today + timedelta(days=days_ahead)
    last_friday_date = friday_date - timedelta(days=7)

    start_date = last_friday_date.strftime("%Y%m%d")
    end_date = friday_date.strftime("%Y%m%d")

    create_db(start_date, end_date)

    excel_list = []
    for config_file in config_list:
        print(f'{config_file}')

        try:
            config = Dynaconf(
                start_date=start_date,
                end_date=end_date,
                settings_files=[config_file]
            )
            excel_name = parse(config)
            excel_list.append(excel_name)
        except Exception as e:
            if send_error:
                send_msg(f'{config_file}\n' + str(e))
            else:
                print(e)

    create_zip(excel_list, "data.zip")
    send_mail()


def create_db(start_date, end_date):
    # 建立SQLite数据库连接
    engine = create_engine(f'sqlite:///data.db')

    # 创建inspect对象
    inspector = inspect(engine)

    for date in pd.date_range(start_date, end_date):
        file_name = date.strftime("%Y%m%d")
        file_path = f"data/{file_name}.csv"
        if os.path.exists(file_path) and not inspector.has_table(file_name):
            try:
                df = pd.read_csv(file_path, encoding='utf-8')
            except:
                df = pd.read_csv(file_path, encoding='gbk')

            df.to_sql(file_name, con=engine, if_exists='replace', index=False)

    # 关闭数据库连接
    engine.dispose()
    return True


def parse(config):
    # 起始日期
    start_date_str = config.start_date
    start_date = datetime.strptime(start_date_str, "%Y%m%d")
    # 结束日期
    end_date_str = config.end_date
    end_date = datetime.strptime(end_date_str, "%Y%m%d")

    ctype = config.ctype
    column = config.column

    # 文件名
    excel_name = config.file_name
    file_name_format = config.file_name_format

    # 筛选条件
    conditions = config.conditions
    if conditions["limit"] != -1:
        RED = '\033[91m'
        RESET = '\033[0m'

        print(RED + f"仅返回前{conditions['limit']}条数据" + RESET)

    column_name = config.column_name

    # 文件名附加日期
    if file_name_format or not excel_name:
        if start_date == end_date:
            excel_name = excel_name + start_date_str
        else:
            excel_name = excel_name + start_date_str + "~" + end_date_str

    # 设置列名
    try:
        data_list = [column_name[ctype]]
    except KeyError:
        print("不存在方法：", ctype)
        return

    total_days = (end_date - start_date).days + 1
    with tqdm(total=total_days, desc="进度", dynamic_ncols=True) as pbar:
        for current_date in range(total_days):
            current_date = start_date + timedelta(days=current_date)

            str_date = current_date.strftime('%Y%m%d')
            pbar.set_postfix_str(str_date)

            # 计算数据
            if ctype == "ratio":
                data_tuple = BondDay.ratio(current_date, conditions, database='data')
            else:
                if column == "":
                    column = input("请输入列名：")
                data_tuple = BondDay.bond_math(current_date, column, conditions, ctype, database='data')

            if data_tuple:
                data_list.append(data_tuple)
            pbar.update(1)

    # 保存数据到Excel
    if len(data_list) > 1:
        FileOperator.save_to_excel(excel_name, data_list)

    return f"{excel_name}.xlsx"


def send_mail():
    env = Env()
    env.read_env()
    email_189 = env.json("EMAIL_189")
    to_email = "chushankeji@163.com"
    from_email = email_189["name"]
    from_password = email_189["password"]
    subject = "债券数据"
    body = "债券数据"
    zip_file = "data.zip"

    # 创建 MIMEMultipart 对象
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    # 添加邮件正文
    msg.attach(MIMEText(body, 'plain'))

    # 添加压缩包附件
    attachment = MIMEBase('application', 'zip')
    with open(zip_file, 'rb') as f:
        attachment.set_payload(f.read())
    encoders.encode_base64(attachment)
    attachment.add_header(
        'Content-Disposition',
        f'attachment; filename="{os.path.basename(zip_file)}"'
    )
    msg.attach(attachment)

    # 连接到 SMTP 服务器并发送邮件
    try:
        server = smtplib.SMTP(email_189["host"], email_189["port"])
        server.starttls()
        server.login(from_email, from_password)
        server.send_message(msg)
        server.quit()
        send_msg("可转债：发送成功")
    except Exception as e:
        send_msg(f"可转债：发送失败: {e}")


# 打包文件为压缩包
def create_zip(files, zip_name):
    with zipfile.ZipFile(zip_name, 'w') as zipf:
        for file in files:
            zipf.write(file)


def send_msg(message, action="qywx", webhook="H", msg_type="text", url="https://api.xbxin.com/msg"):
    data = {
        "message": message,
        "action": action,
        "webhook": webhook,
        "msg_type": msg_type,
    }

    requests.post(url, json=data)


if __name__ == '__main__':
    main()
