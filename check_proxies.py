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
    # 增加请求头，伪装成 Chrome 浏览器，解决 403 Forbidden 错误
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    try:
        print(f"正在从 {JSON_URL} 获取最新数据...")
        response = requests.get(JSON_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # 成功获取后，保存/覆盖本地的 all.json
        with open(LOCAL_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("最新数据获取成功并已保存本地。")
        return data
    except Exception as e:
        print(f"网络获取失败: {e}。尝试使用本地保存的 {LOCAL_JSON_FILE}...")
        if os.path.exists(LOCAL_JSON_FILE):
            try:
                with open(LOCAL_JSON_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("本地的 all.json 文件为空或不是合法的 JSON 格式，放弃读取。")
                return []
        else:
            print("本地没有历史备份文件。")
            return []

def test_single_proxy(proxy_item):
    """测试单个代理的有效性和落地位置"""
    ip = proxy_item.get("ip") 
    if not ip:
        return None

    # 第一步：测试有效性
    try:
        valid_url = VALID_CHECK_API.format(ip)
        valid_resp = requests.get(valid_url, timeout=10)
        if valid_resp.status_code != 200:
            return None
    except Exception:
        return None

    # 第二步：通过 IP 代理访问 ip.sb 验证真实落地国家
    try:
        proxies = {
            "http": f"http://{ip}",
            "https": f"http://{ip}"
        }
        geo_resp = requests.get(GEOIP_API, proxies=proxies, timeout=10)
        if geo_resp.status_code == 200:
            geo_data = geo_resp.json()
            if geo_data.get("country_code") == "US":
                print(f"[成功] 找到有效的美国节点: {ip}")
                return ip
    except Exception:
        return None
        
    return None

def main():
    data = get_proxy_data()
    if not data:
        print("未能获取到任何数据，程序退出。")
        return

    # 兼容处理：确保我们提取到的是一个列表
    proxy_list = []
    if isinstance(data, list):
        proxy_list = data
    elif isinstance(data, dict):
        # 如果返回的是一个字典对象，尝试遍历找出里面的列表
        for key, value in data.items():
            if isinstance(value, list):
                proxy_list.extend(value)
    
    if not proxy_list:
        print("无法从获取的数据中解析出节点列表，请检查 JSON 结构。")
        return

    # 安全筛选：只处理字典类型的元素，避免由于异常数据导致的 'str' object has no attribute 'get' 错误
    cn_us_proxies = [
        item for item in proxy_list 
        if isinstance(item, dict) and item.get("country_cn") == "美国"
    ]
    
    print(f"初步筛选出 {len(cn_us_proxies)} 个标记为美国的节点，开始有效性与落地检测...")
    if len(cn_us_proxies) == 0:
        print("没有找到 country_cn 为美国的节点，检测结束。")
        return

    valid_us_ips = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(test_single_proxy, cn_us_proxies)
        for res in results:
            if res:
                valid_us_ips.append(res)

    print(f"\n检测完成！共得到 {len(valid_us_ips)} 个有效且落地为美国的 IP。")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for ip in valid_us_ips:
            f.write(f"{ip}\n")
    print(f"结果已写入 {OUTPUT_FILE}。")

if __name__ == "__main__":
    main()
