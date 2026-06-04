import re
import json
from flask import Blueprint, request, jsonify, render_template

from app.psb_contacts import CONTACTS

psb_bp = Blueprint("psb", __name__)

COUNTRY_MAP = {
    "CHN": "中国", "USA": "美国", "GBR": "英国", "JPN": "日本",
    "KOR": "韩国", "RUS": "俄罗斯", "DEU": "德国", "FRA": "法国",
    "AUS": "澳大利亚", "CAN": "加拿大", "ITA": "意大利", "ESP": "西班牙",
    "NLD": "荷兰", "CHE": "瑞士", "SGP": "新加坡", "MYS": "马来西亚",
    "THA": "泰国", "VNM": "越南", "IND": "印度", "PHL": "菲律宾",
    "IDN": "印度尼西亚", "BRA": "巴西", "MEX": "墨西哥", "SAU": "沙特阿拉伯",
    "ARE": "阿联酋", "TUR": "土耳其", "ZAF": "南非", "NZL": "新西兰",
    "SWE": "瑞典", "NOR": "挪威", "DNK": "丹麦", "FIN": "芬兰",
    "POL": "波兰", "CZE": "捷克", "AUT": "奥地利", "BEL": "比利时",
    "PRT": "葡萄牙", "GRC": "希腊", "ISR": "以色列", "EGY": "埃及",
    "NGA": "尼日利亚", "ARG": "阿根廷", "CHL": "智利", "COL": "哥伦比亚",
    "PER": "秘鲁", "UKR": "乌克兰", "KAZ": "哈萨克斯坦", "PAK": "巴基斯坦",
    "BGD": "孟加拉国", "MMR": "缅甸", "LAO": "老挝", "KHM": "柬埔寨",
    "HKG": "中国香港", "MAC": "中国澳门", "TWN": "中国台湾",
    "IRL": "爱尔兰", "HRV": "克罗地亚", "HUN": "匈牙利", "ROU": "罗马尼亚",
    "BGR": "保加利亚", "SVK": "斯洛伐克", "SVN": "斯洛文尼亚", "LTU": "立陶宛",
    "LVA": "拉脱维亚", "EST": "爱沙尼亚", "ISL": "冰岛", "CYP": "塞浦路斯",
    "MLT": "马耳他", "LUX": "卢森堡", "MCO": "摩纳哥", "QAT": "卡塔尔",
    "KWT": "科威特", "BHR": "巴林", "OMN": "阿曼", "JOR": "约旦",
    "LBN": "黎巴嫩", "IRQ": "伊拉克", "IRN": "伊朗", "SYR": "叙利亚",
    "YEM": "也门", "NPL": "尼泊尔", "LKA": "斯里兰卡", "MDV": "马尔代夫",
    "MNG": "蒙古", "PRK": "朝鲜", "BRN": "文莱", "TLS": "东帝汶",
    "FJI": "斐济", "PNG": "巴布亚新几内亚", "MAR": "摩洛哥", "DZA": "阿尔及利亚",
    "TUN": "突尼斯", "LBY": "利比亚", "SDN": "苏丹", "ETH": "埃塞俄比亚",
    "KEN": "肯尼亚", "TZA": "坦桑尼亚", "UGA": "乌干达", "GHA": "加纳",
    "CIV": "科特迪瓦", "SEN": "塞内加尔", "CMR": "喀麦隆", "AGO": "安哥拉",
    "VEN": "委内瑞拉", "CUB": "古巴", "BOL": "玻利维亚", "PRY": "巴拉圭",
    "URY": "乌拉圭", "ECU": "厄瓜多尔", "CRI": "哥斯达黎加", "PAN": "巴拿马",
    "GTM": "危地马拉", "DOM": "多米尼加", "JAM": "牙买加", "HTI": "海地",
}


def cn_country_name(code):
    return COUNTRY_MAP.get(code.upper(), code.upper())


def parse_mrz_td3(line1, line2):
    if len(line1) != 44 or len(line2) != 44:
        return None, f"MRZ 格式不正确：标准护照 MRZ 应为 2 行各 44 个字符（当前：行1={len(line1)}，行2={len(line2)}）"

    issuing_state = line1[2:5].replace("<", "").strip()
    nationality = line2[10:13].replace("<", "").strip()
    doc_number = line2[0:9].replace("<", "").strip()
    dob_raw = line2[13:19]
    sex = line2[20]
    expiry_raw = line2[21:27]

    name_part = line1[5:44]
    surnames = []
    given_names = []
    if "<<" in name_part:
        surname_part, given_part = name_part.split("<<", 1)
        surnames = [s for s in surname_part.split("<") if s]
        given_names = [s for s in given_part.split("<") if s]

    def fmt_date(raw):
        if raw.isdigit() and len(raw) == 6:
            yy = int(raw[:2])
            mm = raw[2:4]
            dd = raw[4:6]
            century = "19" if yy >= 70 else "20"
            return f"{century}{raw[:2]}-{mm}-{dd}"
        return raw

    result = {
        "document_type": "护照 (TD3)",
        "issuing_state": cn_country_name(issuing_state),
        "issuing_state_code": issuing_state,
        "surname": " ".join(surnames).upper() if surnames else "",
        "given_name": " ".join(given_names).upper() if given_names else "",
        "passport_number": doc_number,
        "nationality": cn_country_name(nationality),
        "nationality_code": nationality,
        "dob": fmt_date(dob_raw),
        "sex": "男" if sex == "M" else "女" if sex == "F" else sex,
        "expiry": fmt_date(expiry_raw),
    }
    return result, None


def parse_mrz_td2(line1, line2):
    if len(line1) != 36 or len(line2) != 36:
        return None, f"MRZ 格式不正确：护照卡 MRZ 应为 2 行各 36 个字符（当前：行1={len(line1)}，行2={len(line2)}）"

    issuing_state = line1[2:5].replace("<", "").strip()
    nationality = line2[10:13].replace("<", "").strip()
    doc_number = line2[0:9].replace("<", "").strip()
    dob_raw = line2[13:19]
    sex = line2[20]
    expiry_raw = line2[21:27]

    name_part = line1[5:36]
    surnames = []
    given_names = []
    if "<<" in name_part:
        surname_part, given_part = name_part.split("<<", 1)
        surnames = [s for s in surname_part.split("<") if s]
        given_names = [s for s in given_part.split("<") if s]

    def fmt_date(raw):
        if raw.isdigit() and len(raw) == 6:
            yy = int(raw[:2])
            mm = raw[2:4]
            dd = raw[4:6]
            century = "19" if yy >= 70 else "20"
            return f"{century}{raw[:2]}-{mm}-{dd}"
        return raw

    result = {
        "document_type": "护照卡 (TD2)",
        "issuing_state": cn_country_name(issuing_state),
        "issuing_state_code": issuing_state,
        "surname": " ".join(surnames).upper() if surnames else "",
        "given_name": " ".join(given_names).upper() if given_names else "",
        "passport_number": doc_number,
        "nationality": cn_country_name(nationality),
        "nationality_code": nationality,
        "dob": fmt_date(dob_raw),
        "sex": "男" if sex == "M" else "女" if sex == "F" else sex,
        "expiry": fmt_date(expiry_raw),
    }
    return result, None


def parse_mrz(line1, line2):
    line1 = line1.strip().upper()
    line2 = line2.strip().upper()

    if len(line1) == 44 and len(line2) == 44:
        return parse_mrz_td3(line1, line2)
    if len(line1) == 36 and len(line2) == 36:
        return parse_mrz_td2(line1, line2)
    return None, f"MRZ 格式不支持：行1长度 {len(line1)}，行2长度 {len(line2)}。支持标准护照（2×44）和护照卡（2×36）"


@psb_bp.route("/psb/mrz")
def mrz_tool_page():
    return render_template("psb_mrz_tool.html")


@psb_bp.route("/psb/passport-guide")
def passport_guide_page():
    return render_template("psb_passport_guide.html")


@psb_bp.route("/api/psb/parse-mrz", methods=["POST"])
def api_parse_mrz():
    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供 MRZ 数据"}), 400
    line1 = data.get("line1", "").strip()
    line2 = data.get("line2", "").strip()
    if not line1 or not line2:
        return jsonify({"error": "请输入 MRZ 两行内容"}), 400
    result, error = parse_mrz(line1, line2)
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"success": True, "data": result})


@psb_bp.route("/psb/contacts")
def psb_contacts_page():
    return render_template("psb_contacts.html")


@psb_bp.route("/api/psb/contacts", methods=["GET"])
def api_psb_contacts():
    city = request.args.get("city", "").strip()
    province = request.args.get("province", "").strip()

    results = CONTACTS
    if city:
        results = [c for c in CONTACTS if city in c["city"] or city in c["province"]]
    if province:
        results = [c for c in results if province in c["province"]]

    sort_by = request.args.get("sort", "city")
    if sort_by in ("city", "province"):
        results = sorted(results, key=lambda c: c.get(sort_by, ""))

    return jsonify({"contacts": results, "total": len(results), "total_all": len(CONTACTS)})


@psb_bp.route("/api/psb/provinces", methods=["GET"])
def api_psb_provinces():
    provinces = sorted(set(c["province"] for c in CONTACTS))
    return jsonify({"provinces": provinces})
