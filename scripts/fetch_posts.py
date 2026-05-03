import json
import os
import sys
import time
import requests

FORUM_BASE = "https://forum.trae.cn"
REQUEST_DELAY = 2
MAX_RETRIES = 3
MAX_EXCERPT_LEN = 200
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"警告: 配置文件 {CONFIG_PATH} 不存在，使用默认配置")
        return {"categories": {}}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    cat_config = config.get("categories", {})
    for name, cfg in cat_config.items():
        if not isinstance(cfg.get("color"), str) or not cfg["color"].startswith("#"):
            print(f"  警告: 分类 '{name}' 颜色格式无效，使用默认色")
        if not isinstance(cfg.get("visible"), bool):
            print(f"  警告: 分类 '{name}' visible 应为 boolean，已忽略")
    return config


def fetch_json(url, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "TRAE-Post-Aggregator/1.0",
                "Accept": "application/json",
            })
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                print(f"  响应格式异常 (尝试 {attempt+1}/{retries}): 期望 Object")
                if attempt < retries - 1:
                    time.sleep(REQUEST_DELAY * (2 ** attempt))
                continue
            return data
        except requests.exceptions.Timeout:
            print(f"  请求超时 (尝试 {attempt+1}/{retries})")
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * (2 ** attempt))
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else 0
            print(f"  HTTP {status} (尝试 {attempt+1}/{retries})")
            if attempt < retries - 1 and status >= 500:
                time.sleep(REQUEST_DELAY * (2 ** attempt))
            elif status >= 400 and status < 500:
                return None
        except requests.exceptions.ConnectionError as e:
            print(f"  连接失败 (尝试 {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * (2 ** attempt))
        except Exception as e:
            print(f"  请求失败 (尝试 {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * (2 ** attempt))
    return None


def fetch_category_map():
    data = fetch_json(f"{FORUM_BASE}/site.json")
    if not data:
        print("  警告: 无法获取分类列表")
        return {}, {}
    cat_map = {}
    sub_cat_map = {}
    for cat in data.get("categories", []):
        cat_id = cat.get("id")
        name = cat.get("name", "")
        parent_id = cat.get("parent_category_id")
        if cat_id and name:
            if parent_id:
                sub_cat_map[cat_id] = parent_id
            else:
                cat_map[cat_id] = name
    print(f"  顶层大类: {len(cat_map)} 个, 子分类: {len(sub_cat_map)} 个(已忽略)")
    return cat_map, sub_cat_map


def resolve_category_id(cat_id, cat_map, sub_cat_map):
    resolved_id = cat_id
    visited = set()
    max_depth = 10
    depth = 0
    while resolved_id in sub_cat_map and resolved_id not in visited and depth < max_depth:
        visited.add(resolved_id)
        resolved_id = sub_cat_map[resolved_id]
        depth += 1
    if depth >= max_depth:
        print(f"  警告: 分类ID {cat_id} 递归深度超限，使用原始ID")
    return resolved_id, cat_map.get(resolved_id, f"未知分类({resolved_id})")


def get_excluded_ids(config, cat_map, sub_cat_map):
    excluded = set()
    cat_config = config.get("categories", {})
    for cat_id, cat_name in cat_map.items():
        if cat_name in cat_config and not cat_config[cat_name].get("visible", True):
            excluded.add(cat_id)
    for sub_id, parent_id in sub_cat_map.items():
        if parent_id in excluded:
            excluded.add(sub_id)
    return excluded


def fetch_user_profile(username):
    data = fetch_json(f"{FORUM_BASE}/u/{username}.json")
    if not data:
        return None
    user = data.get("user", {})
    if not user:
        return None
    avatar_template = user.get("avatar_template", "")
    avatar_url = ""
    if avatar_template:
        if avatar_template.startswith("//"):
            avatar_url = "https:" + avatar_template.replace("{size}", "120")
        elif avatar_template.startswith("http"):
            avatar_url = avatar_template.replace("{size}", "120")
        else:
            avatar_url = FORUM_BASE + avatar_template.replace("{size}", "120")
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "name": user.get("name", ""),
        "avatar_url": avatar_url,
        "title": user.get("title", ""),
        "website": user.get("website", ""),
        "trust_level": user.get("trust_level", 0),
        "created_at": user.get("created_at", ""),
    }


def fetch_user_topics(username):
    all_topics = []
    seen_ids = set()
    page = 0
    max_pages = 200
    while page < max_pages:
        url = f"{FORUM_BASE}/topics/created-by/{username}.json"
        if page > 0:
            url += f"?page={page}"
        print(f"  正在获取第 {page + 1} 页...")
        data = fetch_json(url)
        if not data:
            print("  获取数据失败，停止翻页")
            break
        topic_list = data.get("topic_list", {})
        if not isinstance(topic_list, dict):
            print("  数据格式异常，停止翻页")
            break
        topics = topic_list.get("topics", [])
        if not topics:
            break
        new_count = 0
        for t in topics:
            tid = t.get("id")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                all_topics.append(t)
                new_count += 1
        if new_count == 0:
            print("  本页无新数据，停止翻页")
            break
        more_url = topic_list.get("more_topics_url", "")
        if not more_url:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    if page >= max_pages:
        print(f"  警告: 达到最大翻页数 {max_pages}，数据可能不完整")
    return all_topics


def resolve_image_url(image_url):
    if not image_url:
        return ""
    if image_url.startswith("http"):
        return image_url
    if image_url.startswith("//"):
        return "https:" + image_url
    if image_url.startswith("/"):
        return FORUM_BASE + image_url
    return FORUM_BASE + "/" + image_url


def truncate_excerpt(excerpt, max_len=MAX_EXCERPT_LEN):
    if not excerpt:
        return ""
    excerpt = excerpt.replace("&hellip;", "...").replace("&amp;", "&")
    excerpt = excerpt.replace("&lt;", "<").replace("&gt;", ">")
    excerpt = excerpt.replace("&quot;", "\"").replace("&#39;", "'")
    if len(excerpt) <= max_len:
        return excerpt
    truncated = excerpt[:max_len - 3].rstrip()
    return truncated + "..."


def process_topic(topic, cat_map, sub_cat_map):
    raw_cat_id = topic.get("category_id", 0)
    cat_id, cat_name = resolve_category_id(raw_cat_id, cat_map, sub_cat_map)
    tags = []
    for t in topic.get("tags", []):
        if isinstance(t, dict):
            tag_name = t.get("name", "")
            if tag_name:
                tags.append(tag_name)
        elif isinstance(t, str) and t:
            tags.append(t)
    excerpt = truncate_excerpt(topic.get("excerpt", ""))
    image_url = resolve_image_url(topic.get("image_url", ""))
    return {
        "id": topic.get("id"),
        "title": topic.get("title", ""),
        "created_at": topic.get("created_at", ""),
        "last_posted_at": topic.get("last_posted_at", ""),
        "category_id": cat_id,
        "category_name": cat_name,
        "tags": tags,
        "excerpt": excerpt,
        "image_url": image_url,
        "views": topic.get("views", 0) or 0,
        "like_count": topic.get("like_count", 0) or 0,
        "reply_count": topic.get("reply_count", 0) or 0,
        "posts_count": topic.get("posts_count", 0) or 0,
        "url": f"{FORUM_BASE}/t/topic/{topic.get('id')}",
        "pinned": topic.get("pinned", False),
        "closed": topic.get("closed", False),
        "archived": topic.get("archived", False),
    }


def validate_posts(posts):
    report = {"total": len(posts), "missing_title": 0, "missing_date": 0,
               "invalid_category": 0, "valid": 0}
    for p in posts:
        issues = 0
        if not p.get("title"):
            report["missing_title"] += 1
            issues += 1
        if not p.get("created_at"):
            report["missing_date"] += 1
            issues += 1
        if "未知分类" in p.get("category_name", ""):
            report["invalid_category"] += 1
            issues += 1
        if issues == 0:
            report["valid"] += 1
    return report


def validate_environment():
    username = os.environ.get("FORUM_USERNAME", "")
    if not username:
        print("错误: 请设置环境变量 FORUM_USERNAME")
        sys.exit(1)
    username = username.strip()
    if not username:
        print("错误: FORUM_USERNAME 不能为空")
        sys.exit(1)
    return username


def fetch_forum_data(username, config):
    print("[1/4] 获取论坛分类列表...")
    cat_map, sub_cat_map = fetch_category_map()
    if not cat_map:
        print("错误: 无法获取分类列表，论坛可能不可用")
        sys.exit(1)
    print(f"  获取到 {len(cat_map)} 个顶层大类")

    excluded_ids = get_excluded_ids(config, cat_map, sub_cat_map)
    excluded_names = [cat_map[i] for i in excluded_ids if i in cat_map]
    print(f"  已排除分类: {', '.join(excluded_names) if excluded_names else '无'}")

    print("[2/4] 获取用户信息...")
    profile = fetch_user_profile(username)
    if not profile:
        profile = {
            "id": None,
            "username": username,
            "name": "",
            "avatar_url": "",
            "title": "",
            "website": "",
            "trust_level": 0,
            "created_at": "",
        }
        print("  警告: 无法获取用户详情，使用基础信息继续")
    else:
        print(f"  用户: {profile['username']} (ID: {profile['id']})")

    print("[3/4] 获取用户帖子...")
    raw_topics = fetch_user_topics(username)
    print(f"  共获取 {len(raw_topics)} 条帖子")

    return cat_map, sub_cat_map, excluded_ids, excluded_names, profile, raw_topics


def process_and_filter_topics(raw_topics, cat_map, sub_cat_map, excluded_ids):
    print("[4/4] 处理和筛选帖子...")
    filtered_topics = []
    excluded_count = 0
    seen_filtered_ids = set()
    for topic in raw_topics:
        cat_id = topic.get("category_id", 0)
        if cat_id in excluded_ids:
            excluded_count += 1
            continue
        if not topic.get("visible", True):
            continue
        tid = topic.get("id")
        if tid and tid in seen_filtered_ids:
            continue
        processed = process_topic(topic, cat_map, sub_cat_map)
        if tid:
            seen_filtered_ids.add(tid)
        filtered_topics.append(processed)
    filtered_topics.sort(key=lambda x: x["created_at"], reverse=True)
    return filtered_topics, excluded_count


def build_output_data(profile, filtered_topics, excluded_count, raw_topics, excluded_names):
    validation = validate_posts(filtered_topics)
    if validation["missing_title"] > 0 or validation["missing_date"] > 0:
        print(f"  数据质量: {validation['valid']}/{validation['total']} 完整, "
              f"缺标题 {validation['missing_title']}, 缺日期 {validation['missing_date']}, "
              f"未知分类 {validation['invalid_category']}")

    categories = {}
    for t in filtered_topics:
        cat = t["category_name"]
        if cat not in categories:
            categories[cat] = 0
        categories[cat] += 1

    output = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user": profile,
        "total_posts": len(filtered_topics),
        "excluded_posts": excluded_count,
        "categories": categories,
        "posts": filtered_topics,
        "_quality": {
            "raw_fetched": len(raw_topics),
            "valid_posts": validation["valid"],
            "total_posts": validation["total"],
            "issues": {
                "missing_title": validation["missing_title"],
                "missing_date": validation["missing_date"],
                "invalid_category": validation["invalid_category"],
            }
        }
    }
    return output, validation


def save_output_file(output_data):
    output_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "posts.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    return output_path


def print_summary(filtered_topics, excluded_count, excluded_names, validation, categories, output_path):
    print(f"\n=== 完成 ===")
    print(f"  有效帖子: {len(filtered_topics)}")
    print(f"  已排除: {excluded_count} ({', '.join(excluded_names) if excluded_names else '无'})")
    print(f"  分类统计: {json.dumps(categories, ensure_ascii=False)}")
    print(f"  数据完整率: {validation['valid']}/{validation['total']}")
    print(f"  输出文件: {output_path}")


def main():
    username = validate_environment()
    config = load_config()
    cat_map, sub_cat_map, excluded_ids, excluded_names, profile, raw_topics = fetch_forum_data(username, config)
    filtered_topics, excluded_count = process_and_filter_topics(raw_topics, cat_map, sub_cat_map, excluded_ids)
    output, validation = build_output_data(profile, filtered_topics, excluded_count, raw_topics, excluded_names)
    output_path = save_output_file(output)
    print_summary(filtered_topics, excluded_count, excluded_names, validation, output["categories"], output_path)


if __name__ == "__main__":
    main()
