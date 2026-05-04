import requests
import json
import os
import concurrent.futures

# 配置常量
JSON_URL = "https://zip.cm.edu.kg/all.json"
LOCAL_JSON_FILE = "all.json"
OUTPUT_FILE = "valid_us_proxies.txt"
VALID_CHECK_API = "https://cpi.bzg.cc.cd/check?proxyip={}"
GEOIP_API = "https://api.ip.sb/geoip"

def get_proxy_data():
    """获取节点数据，优先从网络获取，失败则使用本地历史记录"""
    try:
        print(f"正在从 {JSON_URL} 获取最新数据...")
        response = requests.get(JSON_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # 成功获取后，保存/覆盖本地的 all.json，作为未来的备份
        with open(LOCAL_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("最新数据获取成功并已保存本地。")
        return data
    except Exception as e:
        print(f"网络获取失败: {e}。尝试使用本地保存的 {LOCAL_JSON_FILE}...")
        if os.path.exists(LOCAL_JSON_FILE):
            with open(LOCAL_JSON_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print("本地也没有历史备份，程序退出。")
            return []

def test_single_proxy(proxy_item):
    """测试单个代理的有效性和落地位置"""
    # 假设 JSON 结构中包含 'ip' 字段。如果实际字段名叫其他（比如 'server'），请修改此处
    ip = proxy_item.get("ip") 
    if not ip:
        return None

    # 第一步：测试有效性
    try:
        valid_url = VALID_CHECK_API.format(ip)
        valid_resp = requests.get(valid_url, timeout=10)
        # 假设只要返回 200 即代表该检测 API 认为 IP 有效
        if valid_resp.status_code != 200:
            return None
    except Exception:
        return None

    # 第二步：通过 IP 代理访问 ip.sb 验证真实落地国家
    try:
        # 注意：如果你的 IP 需要指定端口（如 159.60.146.81:443），需确保 ip 变量包含端口
        # 如果默认是 HTTP 代理或 Cloudflare 节点：
        proxies = {
            "http": f"http://{ip}",
            "https": f"http://{ip}"
        }
        
        # 请求 api.ip.sb/geoip 返回 JSON 格式的地理位置信息
        geo_resp = requests.get(GEOIP_API, proxies=proxies, timeout=10)
        if geo_resp.status_code == 200:
            geo_data = geo_resp.json()
            if geo_data.get("country_code") == "US":
                print(f"[成功] 找到有效的美国节点: {ip}")
                return ip
    except Exception:
        # 代理无法连接或超时
        return None
        
    return None

def main():
    data = get_proxy_data()
    if not data:
        return

    # 筛选出初步标记为美国的节点
    # 假设你的 JSON 数据是一个列表，或者你需要从特定的 key 中提取列表
    # 如果 data 是字典结构，请根据实际 JSON 结构调整，例如 data.get("proxies", [])
    cn_us_proxies = [item for item in data if item.get("country_cn") == "美国"]
    print(f"初步筛选出 {len(cn_us_proxies)} 个标记为美国的节点，开始有效性与落地检测...")

    valid_us_ips = []
    # 使用多线程并发检测，显著提高速度（设置20个并发线程）
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(test_single_proxy, cn_us_proxies)
        for res in results:
            if res:
                valid_us_ips.append(res)

    # 将最终有效的结果输出到文件
    print(f"\n检测完成！共得到 {len(valid_us_ips)} 个有效且落地为美国的 IP。")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for ip in valid_us_ips:
            f.write(f"{ip}\n")
    print(f"结果已写入 {OUTPUT_FILE}。")

if __name__ == "__main__":
    main()
