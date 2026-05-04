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
    # 增加 User-Agent 头，伪装成浏览器
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    try:
        print(f"正在从 {JSON_URL} 获取最新数据...")
        response = requests.get(JSON_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # 保存到本地
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
                print("本地文件格式错误，无法解析为 JSON。")
                return []
        else:
            print("未找到本地备份文件。")
            return []

def test_single_proxy(proxy_item):
    """测试单个代理的有效性和落地位置"""
    if not isinstance(proxy_item, dict):
        return None
        
    ip = proxy_item.get("ip") 
    if not ip:
        return None

    try:
        valid_url = VALID_CHECK_API.format(ip)
        valid_resp = requests.get(valid_url, timeout=10)
        if valid_resp.status_code != 200:
            return None
    except Exception:
        return None

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

def extract_proxy_list(data):
    """从不同结构的 JSON 数据中提取出包含代理节点的列表"""
    # 如果根结构就是列表，直接返回
    if isinstance(data, list):
        return data
        
    # 如果根结构是字典，我们需要找到包含数据的那个键
    if isinstance(data, dict):
        # 你的 JSON 数据中，节点列表存在 'data' 这个键下面
        if 'data' in data and isinstance(data['data'], list):
            return data['data']
            
        # 如果不是 'data' 键，尝试遍历寻找第一个列表类型的值
        for key, value in data.items():
            if isinstance(value, list):
                print(f"在键 '{key}' 下找到了节点列表。")
                return value
                
    print("无法从数据中解析出合法的节点列表。")
    return []

def main():
    raw_data = get_proxy_data()
    if not raw_data:
        print("未能获取到任何数据，程序退出。")
        return

    # 提取实际的代理节点列表
    proxy_list = extract_proxy_list(raw_data)
    
    if not proxy_list:
        print("提取节点列表失败，程序退出。")
        return

    # 安全地筛选出美国节点
    cn_us_proxies = [
        item for item in proxy_list 
        if isinstance(item, dict) and item.get("meta", {}).get("country_cn") == "美国"
    ]
    
    print(f"初步筛选出 {len(cn_us_proxies)} 个标记为美国的节点，开始有效性与落地检测...")
    if not cn_us_proxies:
        print("没有找到符合条件的美国节点，检测结束。")
        return

    valid_us_ips = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(test_single_proxy, cn_us_proxies)
        for res in results:
            if res:
                valid_us_ips.append(res)

    print(f"\n检测完成！共得到 {len(valid_us_ips)} 个有效且落地为美国的 IP。")
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_FILE)) or '.', exist_ok=True)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for ip in valid_us_ips:
            f.write(f"{ip}\n")
    print(f"结果已写入 {OUTPUT_FILE}。")

if __name__ == "__main__":
    main()
