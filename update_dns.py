import os
import requests

# 从 GitHub Actions 的环境变量中获取你的机密信息
API_TOKEN = os.environ.get("CF_API_TOKEN")
ZONE_ID = os.environ.get("CF_ZONE_ID")
DOMAIN = os.environ.get("CF_DOMAIN")

FASTEST_FILE = "top_2_fastest.txt"

def get_top_ips():
    """读取并解析文件中的前两个 IP"""
    ips = []
    if not os.path.exists(FASTEST_FILE):
        return ips
    with open(FASTEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                # 文件格式是 "159.60.146.81 # 延迟: 0.50s"，按空格分割取第一项
                ip = line.split()[0]
                ips.append(ip)
    return ips

def update_cf_dns(ips):
    """调用 Cloudflare API 更新 DNS 记录"""
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    base_url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records"

    # 1. 获取当前该域名下所有的 A 记录
    print(f"正在查询 {DOMAIN} 的现有记录...")
    resp = requests.get(base_url, headers=headers, params={"name": DOMAIN, "type": "A"})
    resp.raise_for_status()
    existing_records = resp.json().get("result", [])

    # 2. 删除旧的 A 记录（避免记录无限增加）
    for record in existing_records:
        del_url = f"{base_url}/{record['id']}"
        requests.delete(del_url, headers=headers)
        print(f"已删除旧记录: {record['content']}")

    # 3. 创建新的 A 记录
    for ip in ips:
        payload = {
            "type": "A",
            "name": DOMAIN,
            "content": ip,
            "ttl": 60,       # 设为最短的 TTL (1分钟)，方便快速生效
            "proxied": False # 【核心】必须是 False，以直连优选节点
        }
        res = requests.post(base_url, headers=headers, json=payload)
        if res.status_code == 200:
            print(f"✅ 成功添加新记录: {DOMAIN} -> {ip}")
        else:
            print(f"❌ 添加失败: {res.text}")

if __name__ == "__main__":
    if not all([API_TOKEN, ZONE_ID, DOMAIN]):
        print("缺少 Cloudflare 环境变量配置，请检查 GitHub Secrets！")
        exit(1)
        
    top_ips = get_top_ips()
    if top_ips:
        print(f"准备将以下 IP 更新至 DNS: {top_ips}")
        update_cf_dns(top_ips)
    else:
        print("没有找到最快 IP，放弃更新 DNS。")
