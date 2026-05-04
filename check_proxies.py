import requests
import json
import os
import concurrent.futures
import subprocess

# 配置常量
JSON_URL = "https://zip.cm.edu.kg/all.json"
LOCAL_JSON_FILE = "all.json"
OUTPUT_FILE = "valid_us_proxies.txt"
VALID_CHECK_API = "https://cpi.bzg.cc.cd/check?proxyip={}"

def get_proxy_data():
    """获取节点数据，使用浏览器 UA 防止基础拦截"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        print(f"正在从 {JSON_URL} 获取最新数据...")
        response = requests.get(JSON_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        with open(LOCAL_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("最新数据获取成功并已保存本地。")
        return data
    except Exception as e:
        print(f"网络获取失败: {e}。尝试使用本地历史记录...")
        if os.path.exists(LOCAL_JSON_FILE):
            try:
                with open(LOCAL_JSON_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("本地文件格式错误，无法解析。")
        return []

def extract_proxy_list(data):
    """提取嵌套的 JSON 数组"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if 'data' in data and isinstance(data['data'], list):
            return data['data']
        for key, value in data.items():
            if isinstance(value, list):
                return value
    return []

def test_single_proxy(proxy_item):
    """测试单个节点，返回 (IP, 状态码) 方便统计死因"""
    if not isinstance(proxy_item, dict):
        return (None, "FORMAT_ERR")
        
    ip = proxy_item.get("ip") 
    if not ip:
        return (None, "FORMAT_ERR")
        
    # 获取端口，默认 443
    ports = proxy_item.get("port", [443])
    port = ports[0] if ports else 443

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # 第一步：测试有效性 API
    try:
        valid_url = VALID_CHECK_API.format(ip)
        valid_resp = requests.get(valid_url, headers=headers, timeout=8)
        if valid_resp.status_code != 200:
            return (None, f"API_FAIL_{valid_resp.status_code}") # 记录是 403 还是 500
    except requests.exceptions.RequestException:
        return (None, "API_TIMEOUT")

    # 第二步：测试落地 (ip.sb)
    # 核心魔法：使用 curl --resolve 强行将 api.ip.sb 解析到我们的 CF 节点 IP 上
    cmd = [
        "curl", "-s",
        "--resolve", f"api.ip.sb:{port}:{ip}",
        f"https://api.ip.sb:{port}/geoip",
        "--connect-timeout", "5",
        "--max-time", "10",
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout:
            try:
                geo_data = json.loads(result.stdout)
                if geo_data.get("country_code") == "US":
                    print(f"[成功] 找到美国节点: {ip}")
                    return (ip, "SUCCESS")
                else:
                    return (None, f"GEO_NOT_US_{geo_data.get('country_code')}")
            except json.JSONDecodeError:
                return (None, "GEO_JSON_ERR")
        else:
            return (None, "GEO_CURL_TIMEOUT")
    except Exception:
        return (None, "GEO_SYS_ERR")
        
    return (None, "UNKNOWN_ERR")

def main():
    raw_data = get_proxy_data()
    proxy_list = extract_proxy_list(raw_data)
    
    if not proxy_list:
        print("提取节点列表失败，程序退出。")
        return

    # 初步筛选美国节点
    cn_us_proxies = [
        item for item in proxy_list 
        if isinstance(item, dict) and item.get("meta", {}).get("country_cn") == "美国"
    ]
    
    print(f"初步筛选出 {len(cn_us_proxies)} 个标记为美国的节点，开始测试...")

    valid_us_ips = []
    stats = {}

    # 并发数稍微降低到10，防止第一步的 API 把 GitHub Actions 的 IP 给封了
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(test_single_proxy, cn_us_proxies)
        for res_ip, status in results:
            if status == "SUCCESS" and res_ip:
                valid_us_ips.append(res_ip)
            else:
                stats[status] = stats.get(status, 0) + 1

    # 打印死亡报告
    print("\n" + "="*30)
    print(f"📊 测试统计报告 (共检测 {len(cn_us_proxies)} 个):")
    print(f"✅ 成功找到的 US IP: {len(valid_us_ips)}")
    for reason, count in stats.items():
        print(f"❌ 失败原因 [{reason}]: {count} 个")
    print("="*30 + "\n")

    # 写入文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for ip in valid_us_ips:
            f.write(f"{ip}\n")
    print(f"结果已写入 {OUTPUT_FILE}。")

if __name__ == "__main__":
    main()
