from flask import Blueprint, request, jsonify, render_template

payment_bp = Blueprint("payment", __name__)

# ---- Diagnosis Engine ----

DIAGNOSIS_QUESTIONS = [
    {
        "id": "business_type",
        "label": "您的商户类型是？",
        "options": [
            {"value": "restaurant", "label": "餐饮/餐厅"},
            {"value": "hotel", "label": "酒店/民宿"},
            {"value": "retail", "label": "零售/商店"},
            {"value": "other", "label": "其他服务"},
        ],
    },
    {
        "id": "monthly_volume",
        "label": "预计每月境外收款金额？",
        "options": [
            {"value": "low", "label": "1 万元以下"},
            {"value": "medium", "label": "1 万 — 5 万元"},
            {"value": "high", "label": "5 万元以上"},
        ],
    },
    {
        "id": "customer_type",
        "label": "主要接待的外宾类型？",
        "options": [
            {"value": "mixed", "label": "中外游客都有"},
            {"value": "foreign", "label": "主要是外国游客"},
        ],
    },
    {
        "id": "has_pos",
        "label": "是否已有 POS 刷卡机？",
        "options": [
            {"value": "yes", "label": "有"},
            {"value": "no", "label": "没有"},
        ],
    },
    {
        "id": "tech_level",
        "label": "您的技术操作水平？",
        "options": [
            {"value": "basic", "label": "基础（会使用手机 App）"},
            {"value": "intermediate", "label": "中等（会操作电脑后台）"},
            {"value": "advanced", "label": "熟练（有技术团队或懂 API）"},
        ],
    },
    {
        "id": "settlement_urgency",
        "label": "对结算速度的要求？",
        "options": [
            {"value": "fast", "label": "越快越好（T+0 或 T+1）"},
            {"value": "normal", "label": "正常即可（T+3 左右）"},
        ],
    },
]

SOLUTIONS = {
    "airwallex": {
        "name": "Airwallex 空中云汇",
        "tagline": "全球收款 + 多币种钱包，适合有企业资质的商户（不支持个人开户）",
        "score_rules": {
            "business_type": {"restaurant": 2, "hotel": 2, "retail": 1, "other": 0},
            "monthly_volume": {"low": 1, "medium": 2, "high": 3},
            "customer_type": {"mixed": 2, "foreign": 3},
            "has_pos": {"yes": 1, "no": 2},
            "tech_level": {"basic": -1, "intermediate": 1, "advanced": 2},
            "settlement_urgency": {"fast": 1, "normal": 2},
        },
        "features": [
            "支持 Visa / Mastercard / JCB / Amex / Apple Pay / Google Pay",
            "多币种账户（支持 60+ 币种，换汇加点仅 0.2%）",
            "API 集成，适合自建网站",
            "国内卡收款 2.8%+$0.30，国际卡 4.30%+$0.30",
        ],
        "limitations": [
            "仅限企业/个体工商户（不支持个人开户）",
            "开通周期 3-5 个工作日",
        ],
        "tutorial_slug": "airwallex",
        "url": "https://www.airwallex.com/cn",
        "time": "约 3-5 个工作日",
        "difficulty": "中等",
    },
    "lianlian": {
        "name": "连连国际",
        "tagline": "跨境电商收款平台（亚马逊/TikTok等），费率千二封顶，0汇损",
        "score_rules": {
            "business_type": {"restaurant": 0, "hotel": -1, "retail": 2, "other": 1},
            "monthly_volume": {"low": 3, "medium": 2, "high": 1},
            "customer_type": {"mixed": 1, "foreign": 0},
            "has_pos": {"yes": -1, "no": 1},
            "tech_level": {"basic": 3, "intermediate": 2, "advanced": 0},
            "settlement_urgency": {"fast": 2, "normal": 1},
        },
        "features": [
            "跨境电商平台收款（亚马逊 0.25% 封顶，TikTok 0.2% 封顶）",
            "0 汇损，中国银行间外汇市场实时中间价",
            "支持 130+ 币种，直连 190+ 电商站点",
            "支持个人和企业开户，T+0 到账",
        ],
        "limitations": [
            "主要用于跨境电商收款，线下门店场景有限",
            "外卡覆盖以银联为主，Visa/Mastercard 不如 Airwallex 全面",
        ],
        "tutorial_slug": "lianlian",
        "url": "https://www.lianlianpay.com",
        "time": "约 1-3 个工作日",
        "difficulty": "简单",
    },
    "bank_pos": {
        "name": "银行 POS 机方案",
        "tagline": "利用现有 POS 设备开通外卡功能，费率已降至约 1.5%（2024年6月起降费）",
        "score_rules": {
            "business_type": {"restaurant": 1, "hotel": 2, "retail": 1, "other": 0},
            "monthly_volume": {"low": 2, "medium": 2, "high": 1},
            "customer_type": {"mixed": 1, "foreign": 2},
            "has_pos": {"yes": 3, "no": -2},
            "tech_level": {"basic": 2, "intermediate": 1, "advanced": 0},
            "settlement_urgency": {"fast": 0, "normal": 1},
        },
        "features": [
            "外卡费率已降至约 1.5%（Visa/Mastercard 2024年降费后）",
            "利用现有 POS 设备，无需额外硬件",
            "银行信誉背书，资金安全，支持 DCC 货币转换",
            "各地政府对外卡 POS 有设备补贴政策",
        ],
        "limitations": [
            "开通需到网点办理，部分小银行不支持外卡",
            "需使用营业执照进件的商户版 POS（个人版不支持外卡）",
        ],
        "tutorial_slug": "bank-pos",
        "url": None,
        "time": "约 5-10 个工作日",
        "difficulty": "中等",
    },
}

REASON_TEMPLATES = {
    "airwallex": {
        "monthly_volume=high": "您的月收款额较大，Airwallex 的多币种账户（60+ 币种）和换汇成本仅 0.2% 最适合高流水商户。",
        "customer_type=foreign": "您主要接待外国游客，Airwallex 支持 Visa/Mastercard/JCB/Amex，外卡覆盖最全面。",
        "tech_level=advanced": "您有技术能力，可使用 Airwallex API 集成支付系统，已获中国内地支付牌照。",
        "default": "综合您的收款规模和客群特征，Airwallex 的全球收款能力最匹配您的需求。注意：仅限企业/个体户注册。",
    },
    "lianlian": {
        "monthly_volume=low": "您的月收款额较小，连连国际千二封顶+0汇损的策略适合小额度高频收款。",
        "tech_level=basic": "您偏好手机操作，连连国际 App 管理无需技术背景，1 天完成审核。",
        "default": "连连国际的千二封顶费率和 0 汇损在行业中具优势，尤其适合有电商平台店铺的商户。",
    },
    "bank_pos": {
        "has_pos=yes": "您已有 POS 设备，直接开通外卡功能成本最低。2024 年降费后外卡费率仅约 1.5%，还可申请政府补贴。",
        "default": "银行 POS 方案可复用现有设备，外卡费率已降至约 1.5%（2024年降费后），还可关注当地政府 POS 补贴政策。",
    },
}


def diagnose_payment(answers):
    """Score all solutions and return ranked recommendations."""
    results = []
    for slug, sol in SOLUTIONS.items():
        score = 0
        reasons = []
        for qid, answer in answers.items():
            rules = sol["score_rules"].get(qid, {})
            pts = rules.get(answer, 0)
            score += pts
            # Collect matching reasons
            reason_key = f"{qid}={answer}"
            if reason_key in REASON_TEMPLATES.get(slug, {}):
                reasons.append(REASON_TEMPLATES[slug][reason_key])

        # Default reason if no specific matches
        if not reasons:
            reasons.append(REASON_TEMPLATES.get(slug, {}).get("default", ""))

        results.append({
            "slug": slug,
            "name": sol["name"],
            "tagline": sol["tagline"],
            "score": score,
            "features": sol["features"],
            "limitations": sol["limitations"],
            "tutorial_slug": sol["tutorial_slug"],
            "url": sol["url"],
            "time": sol["time"],
            "difficulty": sol["difficulty"],
            "reason": "；".join(reasons) if reasons else "",
        })

    # Sort by score descending
    results.sort(key=lambda r: r["score"], reverse=True)
    # Mark recommended
    if results:
        results[0]["recommended"] = True
    return results


# ---- Tutorial Content ----

TUTORIALS = {
    "airwallex": {
        "title": "Airwallex 空中云汇接入教程",
        "icon": "credit-card",
        "difficulty": "中等",
        "time": "约 30 分钟注册 + 3-5 天审核",
        "intro": "Airwallex（空中云汇）是全球金融科技公司，已获中国内地支付牌照。支持 60+ 币种的跨境收款和多币种钱包。仅限企业/个体工商户注册，适合有企业资质、需要全面外卡覆盖的商户。",
        "steps": [
            {
                "title": "准备材料",
                "content": "注册前请准备以下材料（均为彩色扫描件，JPG/PNG/PDF，单文件＜10MB）：\n• 营业执照（剩余有效期＞6个月，非三证合一需先变更）\n• 法人身份证正反面（四角完整、无反光、文字清晰）\n• 企业银行账户信息\n• 持股 ≥25% 的所有股东身份证件（UBO 最终受益人信息）\n• 建议额外准备：近3个月水电费账单或银行对账单（地址证明）\n• 如有跨境电商店铺链接（亚马逊、Shopify等），可加速审核",
                "image": "airwallex-step1.png",
            },
            {
                "title": "注册账号",
                "content": "1. 访问 airwallex.com/cn，点击'立即注册'\n2. 选择商业账户类型（跨境卖家必须选企业账户）\n3. 填写企业邮箱（建议用常用邮箱）和法人手机号（接收 6 位验证码）\n4. 企业名称必须与营业执照完全一致（包括标点符号）\n5. 选择经营业务类型，如实填写预计月交易金额\n6. 设置密码，验证邮箱后登录后台",
                "image": "airwallex-step2.png",
            },
            {
                "title": "企业认证（KYC + KYB）",
                "content": "登录后进入认证环节，这是最关键的一步：\n• 上传营业执照彩色扫描件\n• 法人身份证正反面（拍照需光线充足、纯色背景）\n• 提交 UBO（最终受益人）身份证明（持股 ≥25% 的所有股东）\n• 可能要求补充地址证明和资金来源说明\n• 审核时间：通常 3-5 个工作日（48 小时-7 天）\n\n加速技巧：备注'紧急处理 + 预计月交易金额'，客服优先处理。",
                "image": "airwallex-step3.png",
            },
            {
                "title": "安全设置 + 激活账户",
                "content": "审核通过后首次登录必须完成：\n• 开启两步验证（2FA），推荐 Google Authenticator\n• 按团队成员角色设置交易权限分级\n• 完成初始入金（建议最低 500 美元）\n• 优先开通三大主力币种账户：美元、欧元、港币/英镑\n• 绑定电商平台（如亚马逊 SPN）或设置支付链接\n• 可选：设置汇率波动预警、自动换汇规则",
                "image": "airwallex-step4.png",
            },
            {
                "title": "测试交易 + 提现设置",
                "content": "正式使用前建议：\n1. 用一笔小额交易测试收款流程是否正常\n2. 设置提现银行账户（支持工农中建等主流银行）\n3. 确认结算周期和手续费率（国内卡 2.8%+$0.30，国际卡 4.30%+$0.30）\n4. 开启交易通知（短信/邮件）\n5. 资金存放于渣打、DBS 等银行独立隔离账户，受法律保护",
                "image": "airwallex-step5.png",
            },
        ],
        "faq": [
            {"q": "需要什么资质？", "a": "需要中国大陆企业营业执照或个体工商户执照。仅限企业客户，不支持纯个人注册。"},
            {"q": "手续费多少？", "a": "国内卡约 2.8%+$0.30/笔，国际卡约 4.30%+$0.30/笔。换汇加点仅 0.2%，行业最低。无开户费、年费、管理费。"},
            {"q": "钱怎么提到国内？", "a": "在 Airwallex 后台绑定您的国内银行账户（支持工农中建等主流银行），一键提现。到账时间 T+0 或 T+1。"},
            {"q": "审核被拒的常见原因？", "a": "公司名称含敏感词、股东结构复杂且文件不全、经营类目在禁止范围（投资、赌博等）、未在期限内补充材料。"},
        ],
    },
    "lianlian": {
        "title": "连连国际接入教程",
        "icon": "smartphone",
        "difficulty": "简单",
        "time": "约 20 分钟注册 + 1 天审核",
        "intro": "连连国际（LianLian Global）是连连支付旗下的跨境支付品牌，2026 年以'千二封顶 + 0汇损'为核心费率策略。主要服务跨境电商平台收款（亚马逊、TikTok Shop、TEMU 等），支持个人和企业开户。",
        "steps": [
            {
                "title": "准备材料",
                "content": "根据主体类型准备不同材料：\n\n• 个人用户：二代身份证正反面 + 手持身份证照片 + 本人境内借记卡 + 手机号\n• 企业用户：三证合一营业执照彩色扫描件（有效期＞1个月）+ 法人身份证正反面 + 企业对公账户（或法人个人借记卡）+ 电商平台店铺后台截图（显示店铺名称、经营类目、近3个月流水）\n\n所有材料需彩色原件扫描，单文件＜5MB，照片清晰无水印。",
                "image": "lianlian-step1.png",
            },
            {
                "title": "注册账号",
                "content": "1. 访问 global.lianlianpay.com（PC端推荐）或下载连连国际 App\n2. 企业用户务必选择'企业用户注册'通道（不要点错个人入口）\n3. 选择主体所在地（中国大陆/中国香港）\n4. 输入邮箱、手机号及验证码\n5. 设置双重密码（登录密码 + 支付密码），8-32位，含数字+字母\n6. 选择账户类型为'跨境电商'，选细分行业，点击'开启服务'",
                "image": "lianlian-step2.png",
            },
            {
                "title": "申请境外收款账户",
                "content": "1. 进入首页点击'申请收款账户'\n2. 选择目标电商平台（亚马逊、Shopify、Shopee、TikTok Shop 等）\n3. 选择币种（USD、JPY、KRW 等）和银行所在地\n4. 填写店铺名称、链接、持有人名称（企业填公司全称）\n5. 完成平台授权（如 Shopify 需登录店铺确认绑定）\n\n支持 130+ 币种，免费开通 30 国本地收款虚拟账户。",
                "image": "lianlian-step3.png",
            },
            {
                "title": "实名认证（KYC）",
                "content": "1. 选择账户类型（企业/个人）\n2. 按步骤填写主体信息，上传对应证照文件\n3. 企业用户：收款账户公司名必须与电商平台注册主体完全一致\n4. 提交后审核约 1 个工作日（短信/邮件通知结果）\n5. 审核通过后可在首页添加专属客户经理\n\n费率：亚马逊 0.25% 封顶，TikTok/TEMU 等 0.2% 封顶，0 汇损。",
                "image": "lianlian-step4.png",
            },
        ],
        "faq": [
            {"q": "个人可以注册吗？", "a": "可以。连连国际支持个人经营者注册，提交身份证+手持照片+人脸识别即可。"},
            {"q": "支持哪些外币？", "a": "支持 130+ 币种收款（美元、日元、韩元、欧元等），以人民币结算入账，采用中国银行间外汇市场实时中间价（0汇损）。"},
            {"q": "手续费多少？", "a": "跨境电商平台收款费率 0.2%-0.3% 封顶（亚马逊 0.25%，TikTok 0.2%），0 汇损，无开户费和管理费。"},
            {"q": "到账要多久？", "a": "通常 T+0 或 T+1 到账，最快秒级。节假日可能顺延。"},
        ],
    },
    "bank-pos": {
        "title": "银行 POS 机外卡开通教程",
        "icon": "bank",
        "difficulty": "中等",
        "time": "约 40 分钟 + 银行办理时间",
        "intro": "2024 年 6 月起，Visa/Mastercard 在中国大陆完成降费改造，银行 POS 外卡费率从 2%-3% 降至约 1.5%。如果您已有银行 POS 设备，开通外卡功能是成本最低的方案。各地政府对商户新增/升级外卡 POS 设备有补贴。",
        "steps": [
            {
                "title": "确认 POS 机是否支持外卡",
                "content": "先确认您的 POS 机型号是否支持外卡：\n1. 查看 POS 机背面或侧面的型号标签\n2. 致电 POS 机办理银行的商户服务热线\n3. 询问：'我的 POS 机型号是 XXX，能否开通 Visa/Mastercard 外卡收款？'\n\n常见支持外卡的 POS 品牌：联迪、百富、新大陆、惠尔丰\n⚠️ 必须使用营业执照进件的商户版 POS，个人版 POS 不支持境外卡。",
                "image": "bankpos-step1.png",
            },
            {
                "title": "准备申请材料",
                "content": "银行通常要求以下材料：\n• 营业执照（原件 + 复印件）\n• 法人身份证（原件 + 复印件）\n• 银行开户许可证\n• POS 机申请表（银行提供）\n• 门面照片 3 张（外观、收银台、店内环境）\n\n建议提前致电网点确认是否还需要其他材料。关注当地商务局/文旅局的外卡 POS 设备补贴政策。",
                "image": "bankpos-step2.png",
            },
            {
                "title": "前往银行办理",
                "content": "1. 携带所有材料前往开户行\n2. 填写'外卡收单业务申请表'\n3. 签署外卡收单协议（注意：当前费率约 1.5%，确认后写入协议）\n4. 银行提交审核（通常 3-5 个工作日）\n\n审核通过后，银行会远程升级您的 POS 机固件，无需更换设备。",
                "image": "bankpos-step3.png",
            },
            {
                "title": "测试外卡交易 + 低成本补充方案",
                "content": "POS 机升级完成后：\n1. 用 Visa/Mastercard 做小额测试交易（如 ¥1），确认小票打印正常\n2. 确认银行后台看到交易记录\n3. 培训收银员：外国顾客刷卡时选择'外卡'支付\n\n💡 低成本补充方案：引导顾客用微信/支付宝绑定外卡后扫码支付，商户端费率仅 0.21%-0.7%，远低于 POS 外卡刷卡。小额消费场景尤其推荐。",
                "image": "bankpos-step4.png",
            },
        ],
        "faq": [
            {"q": "所有银行都支持外卡吗？", "a": "工农中建交等大型银行都支持。部分城商行和农商行可能不支持，建议办理前先致电确认。"},
            {"q": "外卡手续费多少？", "a": "自 2024 年 6 月降费后，银行 POS 外卡费率约 1.5%。工、农、中、建、交等大行均已执行。第三方支付机构 0.9%-3% 不等。微信/支付宝外卡扫码更优惠（0.21%-0.7%）。"},
            {"q": "需要换 POS 机吗？", "a": "大多数新款 POS 机（2018年以后）通过软件升级即可支持外卡。老旧型号可能需要更换。个人版 POS 不支持外卡。"},
            {"q": "DCC 是什么？", "a": "动态货币转换（Dynamic Currency Conversion）。刷卡时自动将人民币金额转换为顾客本国货币显示，方便外国游客。建议开启。"},
        ],
    },
}


@payment_bp.route("/payment/diagnosis")
def diagnosis_page():
    return render_template("payment_diagnosis.html")


@payment_bp.route("/api/payment/diagnose", methods=["POST"])
def api_diagnose():
    data = request.get_json()
    answers = data.get("answers", {}) if data else {}

    # Validate all questions answered
    required_ids = [q["id"] for q in DIAGNOSIS_QUESTIONS]
    for qid in required_ids:
        if qid not in answers:
            return jsonify({"error": f"请回答所有问题（缺少：{qid}）"}), 400

    results = diagnose_payment(answers)
    return jsonify({"recommendations": results})


@payment_bp.route("/payment/tutorials")
def tutorials_page():
    # Summary data for the index page
    summaries = []
    for slug, t in TUTORIALS.items():
        summaries.append({
            "slug": slug,
            "title": t["title"],
            "icon": t["icon"],
            "difficulty": t["difficulty"],
            "time": t["time"],
            "intro": t["intro"][:120] + "…",
        })
    return render_template("payment_tutorials.html", tutorials=summaries)


@payment_bp.route("/payment/tutorial/<slug>")
def tutorial_detail(slug):
    tutorial = TUTORIALS.get(slug)
    if not tutorial:
        return "Tutorial not found", 404

    # Prev/next nav
    slugs = list(TUTORIALS.keys())
    idx = slugs.index(slug)
    prev_slug = slugs[idx - 1] if idx > 0 else None
    next_slug = slugs[idx + 1] if idx < len(slugs) - 1 else None

    return render_template(
        "payment_tutorial_detail.html",
        tutorial=tutorial,
        slug=slug,
        prev_slug=prev_slug,
        next_slug=next_slug,
        prev_title=TUTORIALS[prev_slug]["title"] if prev_slug else None,
        next_title=TUTORIALS[next_slug]["title"] if next_slug else None,
    )
