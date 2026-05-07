import requests
import json
import os
import concurrent.futures
import subprocess
import time

# 配置常量
JSON_URL = "https://zip.cm.edu.kg/all.json"
LOCAL_JSON_FILE = "all.json"
OUTPUT_FILE = "valid_us_proxies.txt"
FASTEST_FILE = "top_2_fastest.txt"      # 新增：测速最快的前2个IP
HISTORY_FILE = "ip_history.json"        # 新增：记录每次选出的IP及出现次数

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
    """测试单个节点，返回 (IP, 状态码, 延迟秒数)"""
    if not isinstance(proxy_item, dict):
        return (None, "FORMAT_ERR", 0)
        
    ip = proxy_item.get("ip") 
    if not ip:
        return (None, "FORMAT_ERR", 0)
        
    ports = proxy_item.get("port", [443])
    port = ports[0] if ports else 443
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # 第一步：测试有效性 API
    try:
        valid_url = VALID_CHECK_API.format(ip)
        valid_resp = requests.get(valid_url, headers=headers, timeout=8)
        if valid_resp.status_code != 200:
            return (None, f"API_FAIL_{valid_resp.status_code}", 0)
    except requests.exceptions.RequestException:
        return (None, "API_TIMEOUT", 0)

    # 第二步：测试落地与真实延迟 (使用 curl 直连)
    cmd = [
        "curl", "-s",
        "--resolve", f"api.ip.sb:{port}:{ip}",
        f"https://api.ip.sb:{port}/geoip",
        "--connect-timeout", "5",
        "--max-time", "10",
        "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    ]
    
    start_time = time.time() # 开始计时
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        latency = time.time() - start_time # 结算耗时（秒）
        
        if result.returncode == 0 and result.stdout:
            try:
                geo_data = json.loads(result.stdout)
                
                # 【核心修改点】：提取落地 IP，判断是否为 IPv6
                egress_ip = geo_data.get("ip", "")
                if ":" in egress_ip:
                    # 如果包含冒号，说明是 IPv6，标记原因并直接抛弃
                    return (None, "REJECT_IPV6_EGRESS", 0)

                if geo_data.get("country_code") == "US":
                    # 打印时顺便把纯净的 IPv4 落地地址也显示出来
                    print(f"[成功] 找到美国 IPv4 节点: {ip} | 落地IP: {egress_ip} | 延迟: {latency:.2f}s")
                    return (ip, "SUCCESS", latency)
                else:
                    return (None, f"GEO_NOT_US_{geo_data.get('country_code')}", 0)
            except json.JSONDecodeError:
                return (None, "GEO_JSON_ERR", 0)
        else:
            return (None, "GEO_CURL_TIMEOUT", 0)
    except Exception:
        return (None, "GEO_SYS_ERR", 0)
        
    return (None, "UNKNOWN_ERR", 0)
def main():
    raw_data = get_proxy_data()
    proxy_list = extract_proxy_list(raw_data)
    
    if not proxy_list:
        print("提取节点列表失败，程序退出。")
        return

    cn_us_proxies = [
        item for item in proxy_list 
        if isinstance(item, dict) and item.get("meta", {}).get("country_cn") == "美国"
    ]
    
    print(f"初步筛选出 {len(cn_us_proxies)} 个标记为美国的节点，开始测试...")

    valid_us_ips_with_latency = [] # 存储 (IP, 延迟) 元组
    stats = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(test_single_proxy, cn_us_proxies)
        for res_ip, status, latency in results:
            if status == "SUCCESS" and res_ip:
                valid_us_ips_with_latency.append((res_ip, latency))
            else:
                stats[status] = stats.get(status, 0) + 1

    # ---- 数据处理与输出 ----
    print("\n" + "="*30)
    print(f"📊 测试统计报告 (共检测 {len(cn_us_proxies)} 个):")
    print(f"✅ 成功找到的 US IP: {len(valid_us_ips_with_latency)}")
    for reason, count in stats.items():
        print(f"❌ 失败原因 [{reason}]: {count} 个")
    print("="*30 + "\n")

    if not valid_us_ips_with_latency:
        print("没有可用的IP，结束输出。")
        return

    # 1. 提取全量有效IP并写入常规 txt 文件
    just_ips = [item[0] for item in valid_us_ips_with_latency]
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for ip in just_ips:
            f.write(f"{ip}\n")
    print(f"全量结果已写入 {OUTPUT_FILE}")

    # 2. 选出延迟最低的 2 个 IP，写入 top_2_fastest.txt
    valid_us_ips_with_latency.sort(key=lambda x: x[1]) # 按延迟（元组的第二个元素）从小到大排序
    top_2 = valid_us_ips_with_latency[:2] # 即使不足2个，Python切片也会安全处理
    
    with open(FASTEST_FILE, 'w', encoding='utf-8') as f:
        for ip, lat in top_2:
            # 顺便把延迟附在后面方便你看（如果你的系统只需要纯IP，把 f.write 改为 f.write(f"{ip}\n") 即可）
            f.write(f"{ip} # 延迟: {lat:.2f}s\n") 
    print(f"最快的前两名已写入 {FASTEST_FILE}")

    # 3. 更新历史出现次数记录到 ip_history.json
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            print("历史文件读取失败，将创建新文件。")
            history = {}

    for ip in just_ips:
        history[ip] = history.get(ip, 0) + 1

    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"历史有效次数已更新至 {HISTORY_FILE}")

if __name__ == "__main__":
    main()
