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
        "tagline": "全球收款 + 多币种钱包，适合有技术能力的中大规模商户",
        "score_rules": {
            "business_type": {"restaurant": 2, "hotel": 2, "retail": 1, "other": 0},
            "monthly_volume": {"low": 1, "medium": 2, "high": 3},
            "customer_type": {"mixed": 2, "foreign": 3},
            "has_pos": {"yes": 1, "no": 2},
            "tech_level": {"basic": -1, "intermediate": 1, "advanced": 2},
            "settlement_urgency": {"fast": 1, "normal": 2},
        },
        "features": [
            "支持 Visa / Mastercard / JCB / 银联",
            "多币种账户（支持 60+ 币种）",
            "API 集成，适合自建网站",
            "支持线上支付 + 线下扫码",
        ],
        "limitations": [
            "需要企业资质（营业执照）",
            "开通周期 3-5 个工作日",
        ],
        "tutorial_slug": "airwallex",
        "url": "https://www.airwallex.com/cn",
        "time": "约 3-5 个工作日",
        "difficulty": "中等",
    },
    "lianlian": {
        "name": "连连国际",
        "tagline": "操作简单，App 即可管理，适合中小商户",
        "score_rules": {
            "business_type": {"restaurant": 2, "hotel": 1, "retail": 2, "other": 1},
            "monthly_volume": {"low": 3, "medium": 2, "high": 1},
            "customer_type": {"mixed": 2, "foreign": 1},
            "has_pos": {"yes": 1, "no": 2},
            "tech_level": {"basic": 3, "intermediate": 2, "advanced": 0},
            "settlement_urgency": {"fast": 2, "normal": 1},
        },
        "features": [
            "支持微信 / 支付宝 / 银联",
            "简单 App 操作，无需技术背景",
            "到账速度快（T+0 或 T+1）",
            "支持个人和企业开户",
        ],
        "limitations": [
            "外卡覆盖不如 Airwallex 全面",
            "多币种支持有限（主要是人民币结算）",
        ],
        "tutorial_slug": "lianlian",
        "url": "https://www.lianlianpay.com",
        "time": "约 1-3 个工作日",
        "difficulty": "简单",
    },
    "bank_pos": {
        "name": "银行 POS 机方案",
        "tagline": "利用现有 POS 设备开通外卡功能，适合已有 POS 的商户",
        "score_rules": {
            "business_type": {"restaurant": 1, "hotel": 2, "retail": 1, "other": 0},
            "monthly_volume": {"low": 2, "medium": 2, "high": 1},
            "customer_type": {"mixed": 1, "foreign": 2},
            "has_pos": {"yes": 3, "no": -2},
            "tech_level": {"basic": 2, "intermediate": 1, "advanced": 0},
            "settlement_urgency": {"fast": 0, "normal": 1},
        },
        "features": [
            "利用现有 POS 设备，无需额外硬件",
            "银行信誉背书，资金安全",
            "支持 DCC 动态货币转换",
            "部分银行支持上门办理",
        ],
        "limitations": [
            "开通可能需到网点办理",
            "费率相对较高（2%-3%）",
            "部分小银行不支持外卡",
        ],
        "tutorial_slug": "bank-pos",
        "url": None,
        "time": "约 5-10 个工作日",
        "difficulty": "中等",
    },
}

REASON_TEMPLATES = {
    "airwallex": {
        "monthly_volume=high": "您的月收款额较大，Airwallex 的多币种账户和批量结算功能最适合高流水商户。",
        "customer_type=foreign": "您主要接待外国游客，Airwallex 对 Visa/Mastercard/JCB 的覆盖最全面。",
        "tech_level=advanced": "您有技术能力，可以使用 Airwallex 的 API 集成自己的支付系统。",
        "default": "综合您的收款规模和客群特征，Airwallex 的全球收款能力最匹配您的需求。",
    },
    "lianlian": {
        "monthly_volume=low": "您的月收款额较小，连连国际的低门槛和简单操作最适合小额收款场景。",
        "tech_level=basic": "您偏好手机操作，连连国际的 App 管理无需任何技术背景。",
        "default": "基于您的操作习惯和业务规模，连连国际的简单接入方式最适合您。",
    },
    "bank_pos": {
        "has_pos=yes": "您已有 POS 设备，直接开通外卡功能成本最低、最便捷。",
        "default": "银行 POS 方案可以复用您现有的支付设备，降低接入成本。",
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
        "time": "约 30 分钟",
        "intro": "Airwallex（空中云汇）是一家全球金融科技公司，支持 60+ 币种的跨境收款和多币种钱包。适合有企业资质、需要全面外卡覆盖的商户。",
        "steps": [
            {
                "title": "注册账号",
                "content": "访问 airwallex.com/cn，点击'注册'。填写企业邮箱和手机号，设置密码。注意：请使用企业邮箱（如 admin@yourbusiness.com），不要使用个人邮箱。注册后查收验证邮件并激活账号。",
                "image": "airwallex-step1.png",
            },
            {
                "title": "企业认证（KYC）",
                "content": "登录后，系统会引导您完成企业认证。需要准备以下材料：\n• 营业执照（彩色扫描件或清晰照片）\n• 法人身份证正反面\n• 企业银行账户信息\n• 公司注册地址证明（如租赁合同）\n\n按提示上传材料，通常 1-2 个工作日内审核完成。",
                "image": "airwallex-step2.png",
            },
            {
                "title": "开通全球收款账户",
                "content": "认证通过后，进入'全球收款'页面：\n1. 点击'开通新账户'\n2. 选择需要的币种（建议至少开通 USD、EUR、GBP、JPY）\n3. 系统会自动生成对应币种的收款账户\n\n开通后，您将获得各币种的银行账号，外国游客可以直接用本地货币付款。",
                "image": "airwallex-step3.png",
            },
            {
                "title": "绑定支付方式",
                "content": "根据您的业务场景选择：\n• 线上收款：将 Airwallex 生成的支付链接嵌入您的网站或社交媒体\n• 线下收款：下载 Airwallex 商户 App，生成收款二维码，顾客扫码支付\n• API 集成：如果您有技术团队，使用 Airwallex API 定制支付流程\n\n注意：线下二维码支持 Visa/Mastercard/JCB/银联。",
                "image": "airwallex-step4.png",
            },
            {
                "title": "测试交易 + 提现设置",
                "content": "正式使用前，建议：\n1. 用一笔小额交易（如 ¥1）测试收款流程是否正常\n2. 设置提现银行账户（中国大陆银行均可）\n3. 确认结算周期和手续费率\n4. 开启交易通知（短信/邮件）\n\n全部完成后，您的 Airwallex 即可正式投入使用。",
                "image": "airwallex-step5.png",
            },
        ],
        "faq": [
            {"q": "需要什么资质？", "a": "需要中国大陆企业营业执照。个体工商户也可以，但需要提供经营者身份证。"},
            {"q": "手续费多少？", "a": "外卡收款费率约 2.8%+¥0.3/笔。大额交易可联系客户经理协商费率。"},
            {"q": "钱怎么提到国内？", "a": "在 Airwallex 后台绑定您的国内银行账户（支持工农中建等主流银行），一键提现。到账时间 T+0 或 T+1。"},
            {"q": "没有网站可以用吗？", "a": "可以。Airwallex 提供支付链接和二维码收款，不需要网站。"},
        ],
    },
    "lianlian": {
        "title": "连连国际接入教程",
        "icon": "smartphone",
        "difficulty": "简单",
        "time": "约 20 分钟",
        "intro": "连连国际（LianLian Global）是连连支付旗下的跨境支付品牌，支持微信/支付宝/银联收款，操作简单，适合中小商户和个人经营者。",
        "steps": [
            {
                "title": "下载 App 并注册",
                "content": "1. 在应用商店搜索'连连国际'下载 App\n2. 使用手机号注册（支持中国大陆手机号）\n3. 设置登录密码和支付密码\n4. 完成手机号验证",
                "image": "lianlian-step1.png",
            },
            {
                "title": "实名认证",
                "content": "连连国际支持个人和企业两种认证方式：\n• 个人：提交身份证正反面 + 人脸识别\n• 企业：提交营业执照 + 法人身份证\n\n个人认证通常在几分钟内完成，企业认证需要 1 个工作日。",
                "image": "lianlian-step2.png",
            },
            {
                "title": "开通收款服务",
                "content": "认证通过后，在 App 首页选择'跨境收款'：\n1. 选择收款币种（支持 USD、JPY、KRW 等）\n2. 绑定结算银行卡（国内借记卡即可）\n3. 设置汇率提醒（可选，帮助您在合适时机提现）\n\n注意：连连主要是人民币结算，外卡覆盖以银联为主。",
                "image": "lianlian-step3.png",
            },
            {
                "title": "生成收款码 + 开始使用",
                "content": "1. 在 App 中生成收款二维码\n2. 打印二维码，放在收银台或前台\n3. 外国游客扫码即可支付（支持微信/支付宝国际版）\n\n也可以在手机端生成支付链接，发送给顾客。",
                "image": "lianlian-step4.png",
            },
        ],
        "faq": [
            {"q": "个人可以注册吗？", "a": "可以。连连国际支持个人经营者注册，提交身份证+人脸识别即可。"},
            {"q": "支持哪些外币？", "a": "主要是人民币结算。支持美元、日元、韩元等币种收款，但会转换为人民币到账。"},
            {"q": "手续费多少？", "a": "费率约 1%-2%，根据收款币种和金额不同。小额收款手续费更低。"},
            {"q": "到账要多久？", "a": "通常 T+0 或 T+1 到账，节假日可能顺延。"},
        ],
    },
    "bank-pos": {
        "title": "银行 POS 机外卡开通教程",
        "icon": "bank",
        "difficulty": "中等",
        "time": "约 40 分钟 + 银行办理时间",
        "intro": "如果您已有银行的 POS 刷卡机，可以直接联系银行开通外卡收款功能。这是成本最低的方案，无需更换设备、无需重新对接。",
        "steps": [
            {
                "title": "确认 POS 机是否支持外卡",
                "content": "先确认您的 POS 机型号是否支持外卡：\n1. 查看 POS 机背面或侧面的型号标签\n2. 致电 POS 机办理银行的商户服务热线\n3. 询问：'我的 POS 机型号是 XXX，能否开通 Visa/Mastercard 外卡收款？'\n\n常见支持外卡的 POS 品牌：联迪、百富、新大陆、惠尔丰",
                "image": "bankpos-step1.png",
            },
            {
                "title": "准备申请材料",
                "content": "银行通常要求以下材料：\n• 营业执照（原件 + 复印件）\n• 法人身份证（原件 + 复印件）\n• 银行开户许可证\n• POS 机申请表（银行提供）\n• 门面照片 3 张（外观、收银台、店内环境）\n\n建议提前致电网点确认是否还需要其他材料。",
                "image": "bankpos-step2.png",
            },
            {
                "title": "前往银行办理",
                "content": "1. 携带所有材料前往开户行\n2. 填写'外卡收单业务申请表'\n3. 签署外卡收单协议（注意阅读费率条款）\n4. 银行提交审核（通常 3-5 个工作日）\n\n审核通过后，银行会远程升级您的 POS 机固件，无需更换设备。",
                "image": "bankpos-step3.png",
            },
            {
                "title": "测试外卡交易",
                "content": "POS 机升级完成后：\n1. 用一张 Visa/Mastercard 做小额测试交易（如 ¥1）\n2. 确认小票打印正常，显示外卡标识\n3. 确认银行后台看到交易记录\n4. 培训收银员：外国顾客刷卡时选择'外卡'支付\n\n注意：外卡交易结算周期通常为 T+3，比银联卡慢。建议预留资金周转。",
                "image": "bankpos-step4.png",
            },
        ],
        "faq": [
            {"q": "所有银行都支持外卡吗？", "a": "工农中建交等大型银行都支持。部分城商行和农商行可能不支持，建议办理前先致电确认。"},
            {"q": "外卡手续费多少？", "a": "通常 2%-3%。Visa/Mastercard 标准费率约 2.2%，具体以银行协议为准。"},
            {"q": "需要换 POS 机吗？", "a": "大多数新款 POS 机（2018年以后）通过软件升级即可支持外卡。老旧型号可能需要更换。"},
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
