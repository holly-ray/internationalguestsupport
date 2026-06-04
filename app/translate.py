import os
import sys
import json
from urllib.request import Request, urlopen
from urllib.error import URLError
from flask import Blueprint, request, jsonify, session

from app.rate_limit import rate_limit
from app.auth import login_required
from app.constants import HISTORY_MAX_ENTRIES, HISTORY_TTL

translate_bp = Blueprint("translate", __name__)

PROMPTS = {
    "menu": {
        "en": (
            "You are a professional restaurant menu translator. "
            "Translate Chinese menu items into natural, appetizing English.\n\n"
            "Rules:\n"
            "- Dish names: use standard English culinary terms\n"
            "- Include main ingredients in descriptions\n"
            "- Mark allergens with emojis: nuts🥜 shellfish🦐 dairy🥛 gluten🌾 eggs🥚 fish🐟\n"
            "- Keep numbered list format\n"
            "- Output ONLY the translated menu, no other text"
        ),
        "ja": (
            "あなたはプロの料理メニュー翻訳者です。中国語のメニューを自然な日本語に翻訳してください。\n\n"
            "ルール：\n"
            "- 料理名はカタカナを適切に使用\n"
            "- 主な食材を説明に含める\n"
            "- アレルギー物質を絵文字で表示：🥜ナッツ 🦐甲殻類 🥛乳製品 🌾小麦 🥚卵 🐟魚\n"
            "- 番号付きリストはそのまま維持\n"
            "- 翻訳後のメニューのみを出力"
        ),
        "ko": (
            "당신은 전문 레스토랑 메뉴 번역가입니다. 중국어 메뉴를 자연스러운 한국어로 번역하세요.\n\n"
            "규칙:\n"
            "- 요리 이름은 표준 외래어 표기법 사용\n"
            "- 주요 재료를 설명에 포함\n"
            "- 알레르기 유발 식품을 이모지로 표시: 🥜견과류 🦐갑각류 🥛유제품 🌾밀 🥚계란 🐟생선\n"
            "- 번호 목록 유지\n"
            "- 번역된 메뉴만 출력"
        ),
        "ru": (
            "Вы профессиональный переводчик меню ресторанов. "
            "Переведите китайское меню на естественный русский язык.\n\n"
            "Правила:\n"
            "- Названия блюд: устоявшиеся переводы или транслитерация\n"
            "- Укажите основные ингредиенты\n"
            "- Отметьте аллергены эмодзи: 🥜орехи 🦐морепродукты 🥛молочное 🌾глютен 🥚яйца 🐟рыба\n"
            "- Сохраните нумерацию\n"
            "- Выведите ТОЛЬКО переведенное меню"
        ),
    },
    "checkin_guide": {
        "en": (
            "You are a hotel guest service specialist. "
            "Translate Chinese hotel/homestay guides into warm, welcoming English.\n\n"
            "Rules:\n"
            "- Use friendly, hospitable tone\n"
            "- Keep all details accurate (times, phone numbers, prices)\n"
            "- Use ⏰ for times, 📞 for phone, 🔑 for keys, 🚿 for bathroom, 🚫 for don't\n"
            "- Add 'Need help?' line at end\n"
            "- Output ONLY the translated guide"
        ),
        "ja": (
            "あなたはホテルのゲストサービス専門家です。"
            "中国語の宿泊ガイドを温かみのある日本語に翻訳してください。\n\n"
            "ルール：\n"
            "- 親しみやすく丁寧なトーン\n"
            "- 時間・電話番号・料金などの重要情報を正確に\n"
            "- ⏰時間 📞電話 🔑パスワード 🚿バスルーム 🚫禁止事項\n"
            "- 最後に「お困りですか？」とフロント連絡先を記載\n"
            "- 翻訳後のガイドのみを出力"
        ),
        "ko": (
            "당신은 호텔 게스트 서비스 전문가입니다. "
            "중국어 숙박 가이드를 따뜻하고 환영하는 한국어로 번역하세요.\n\n"
            "규칙:\n"
            "- 친절하고 환대하는 어조\n"
            "- 시간, 전화번호, 가격 등 중요 정보를 정확하게\n"
            "- ⏰시간 📞전화 🔑비밀번호 🚿욕실 🚫금지사항\n"
            "- 명확한 섹션 구분\n"
            "- 마지막에 '도움이 필요하세요?' + 프론트 연락처 추가\n"
            "- 번역된 가이드만 출력"
        ),
        "ru": (
            "Вы специалист по гостевому сервису. "
            "Переведите руководство по проживанию на тёплый, гостеприимный русский язык.\n\n"
            "Правила:\n"
            "- Дружелюбный, приветливый тон\n"
            "- Точность важной информации (время, телефоны, цены)\n"
            "- Используйте ⏰время 📞телефон 🔑пароль 🚿ванная 🚫запрещено\n"
            "- Чёткие разделы\n"
            "- В конце: 'Нужна помощь?' + контакт ресепшн\n"
            "- Выведите ТОЛЬКО переведённое руководство"
        ),
    },
    "room_card": {
        "en": (
            "You are a hotel marketing copywriter. "
            "Translate Chinese room descriptions into attractive English.\n\n"
            "Rules:\n"
            "- Professional yet warm tone\n"
            "- Use ✓ for included, ✗ for not included\n"
            "- Convert ㎡ to sqm\n"
            "- Keep prices in ¥\n"
            "- Add short tagline at top\n"
            "- Output ONLY the translated description"
        ),
        "ja": (
            "あなたはホテルのマーケティングコピーライターです。"
            "中国語の客室説明を魅力的で正確な日本語に翻訳してください。\n\n"
            "ルール：\n"
            "- プロかつ温かみのあるトーン\n"
            "- 設備ありは✓、なしは✗\n"
            "- 面積は平方メートル表記\n"
            "- 価格は¥のまま\n"
            "- 最初に短いキャッチコピー\n"
            "- 翻訳後の客室説明のみを出力"
        ),
        "ko": (
            "당신은 호텔 마케팅 카피라이터입니다. "
            "중국어 객실 설명을 매력적이고 정확한 한국어로 번역하세요.\n\n"
            "규칙:\n"
            "- 전문적이면서 따뜻한 어조\n"
            "- 포함 시설은 ✓, 미포함은 ✗\n"
            "- 면적은 제곱미터로 표기\n"
            "- 가격은 ¥ 그대로\n"
            "- 상단에 짧은 태그라인 추가\n"
            "- 번역된 객실 설명만 출력"
        ),
        "ru": (
            "Вы копирайтер отельного маркетинга. "
            "Переведите описание номера на привлекательный, точный русский язык.\n\n"
            "Правила:\n"
            "- Профессиональный, но тёплый тон\n"
            "- Включено: ✓, не включено: ✗\n"
            "- Площадь в кв.м\n"
            "- Цены в ¥\n"
            "- Короткий слоган сверху\n"
            "- Выведите ТОЛЬКО переведённое описание"
        ),
    },
    "reg_card": {
        "en": (
            "You are translating a hotel registration reminder card. "
            "Translate into clear, simple English.\n\n"
            'Include: "Welcome! Please present your passport.", '
            'check-in/out times, "Thank you for your cooperation!". '
            "Be friendly and short."
        ),
        "ja": (
            "外国人宿泊者向けのホテル登記リマインダーカードを翻訳しています。"
            "明確で丁寧な日本語に翻訳してください。\n\n"
            "含める内容：「ようこそ！パスポートをご提示ください」、"
            "チェックイン/アウト時間、「ご協力ありがとうございます」。簡潔に。"
        ),
        "ko": (
            "외국인 투숙객을 위한 호텔 등록 안내 카드를 번역합니다. "
            "명확하고 공손한 한국어로 번역하세요.\n\n"
            "포함: '환영합니다! 여권을 제시해 주세요', "
            "체크인/아웃 시간, '협조해 주셔서 감사합니다!'. 짧고 공손하게."
        ),
        "ru": (
            "Переведите регистрационную карточку отеля для иностранных гостей "
            "на ясный, вежливый русский язык.\n\n"
            "Включите: приветствие, просьбу предъявить паспорт, "
            "время заезда/выезда, благодарность. Кратко."
        ),
    },
    "emergency_card": {
        "en": (
            "You are translating an emergency contact card for foreign travelers. "
            "Translate into clear, reassuring English.\n\n"
            "Include: Police 110, Ambulance 120, Fire 119, Hotel front desk number, "
            "'Stay calm and call the appropriate number', 'Show this card for help'. "
            "Keep it simple and reassuring."
        ),
        "ja": (
            "外国人旅行者向けの緊急連絡先カードを翻訳しています。"
            "明確で安心感のある日本語に翻訳してください。\n\n"
            "含める内容：警察110、救急車120、消防119、ホテルフロント番号、"
            "「緊急時は落ち着いて適切な番号に電話」「このカードを見せて助けを求めて」。"
        ),
        "ko": (
            "외국인 여행자를 위한 비상 연락처 카드를 번역합니다. "
            "명확하고 안심이 되는 한국어로 번역하세요.\n\n"
            "포함: 경찰 110, 구급차 120, 소방 119, 호텔 프론트 번호, "
            "'비상시 침착하게 해당 번호로 연락', '이 카드를 보여주면 도움을 받을 수 있습니다'."
        ),
        "ru": (
            "Переведите карточку экстренных контактов для иностранных туристов "
            "на ясный, успокаивающий русский язык.\n\n"
            "Включите: Полиция 110, Скорая 120, Пожарная 119, ресепшн отеля, "
            "'Сохраняйте спокойствие и звоните по нужному номеру', "
            "'Покажите эту карточку для помощи'."
        ),
    },
}

MATERIAL_TYPES = [
    {"id": "menu", "label": "菜单/菜品", "icon": "utensils"},
    {"id": "checkin_guide", "label": "入住指南", "icon": "home"},
    {"id": "room_card", "label": "房型介绍", "icon": "door-open"},
    {"id": "reg_card", "label": "登记提示卡", "icon": "id-card"},
    {"id": "emergency_card", "label": "紧急联系卡", "icon": "phone"},
]

LANGUAGES = [
    {"code": "en", "label": "English", "flag": "🇬🇧"},
    {"code": "ja", "label": "日本語", "flag": "🇯🇵"},
    {"code": "ko", "label": "한국어", "flag": "🇰🇷"},
    {"code": "ru", "label": "Русский", "flag": "🇷🇺"},
]


def _check_auth():
    """Check auth and rate limit. Returns (error_response, status) or None if allowed."""
    require_auth = os.getenv("REQUIRE_AUTH", "false").strip().lower()
    if require_auth != "true":
        return None
    from flask import session
    if "user_id" not in session:
        return jsonify({"error": "请先登录"}), 401
    from app.auth import check_rate_limit, _get_user_limit
    if not check_rate_limit(session["user_id"]):
        limit = _get_user_limit(session["user_id"])
        return jsonify({"error": f"今日翻译次数已用完（每日限额 {limit} 次）"}), 429
    return None


@translate_bp.route("/api/translate", methods=["POST"])
@rate_limit("translate", identifier_fn=lambda: session.get("user_id", "anon"))
def translate():
    try:
        auth_err = _check_auth()
        if auth_err:
            return auth_err
        data = request.get_json()
        source_text = data.get("sourceText", "")
        material_type = data.get("materialType", "")
        target_lang = data.get("targetLang", "")

        if not source_text or not material_type or not target_lang:
            return jsonify({"error": "missing required fields"}), 400

        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return jsonify({"error": "API key not configured"}), 500

        system_prompt = PROMPTS.get(material_type, {}).get(target_lang, "")
        if not system_prompt:
            system_prompt = (
                f"You are a professional translator. "
                f"Translate the following Chinese text into {target_lang}. "
                f"Output ONLY the translation."
            )

        req_body = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": source_text},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }).encode("utf-8")

        req = Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=req_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
        translated = body["choices"][0]["message"]["content"]

        # Record translation history
        try:
            from flask import session
            from app.kv_client import redis_get, redis_set, redis_incr
            from datetime import datetime, timezone

            user_id = session.get("user_id")
            if user_id:
                entry = {
                    "material_type": material_type,
                    "target_lang": target_lang,
                    "source_preview": source_text[:80],
                    "translated_preview": translated[:80],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                raw = redis_get(f"history:{user_id}")
                try:
                    history = json.loads(raw) if raw else []
                except (json.JSONDecodeError, TypeError):
                    history = []
                history.append(entry)
                redis_set(f"history:{user_id}", json.dumps(history[-HISTORY_MAX_ENTRIES:], ensure_ascii=False), ex=HISTORY_TTL)
                redis_incr(f"total:{user_id}")
        except Exception:
            pass

        return jsonify({"translatedText": translated})
    except URLError as e:
        try:
            from app.beta import log_error_to_kv
            log_error_to_kv("translate", "DeepSeek API URLError", str(e.reason))
        except Exception:
            pass
        return jsonify({"error": f"Translation failed: {str(e.reason)}"}), 500
    except Exception as e:
        try:
            from app.beta import log_error_to_kv
            log_error_to_kv("translate", "Translation exception", str(e))
        except Exception:
            pass
        return jsonify({"error": f"Translation failed: {str(e)}"}), 500




@translate_bp.route("/api/export-pdf", methods=["POST"])
@login_required
@rate_limit("export")
def export_pdf():
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    data = request.get_json()
    results = data.get("results", [])
    material_type = data.get("materialType", "")

    type_label = next(
        (t["label"] for t in MATERIAL_TYPES if t["id"] == material_type), ""
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"{type_label} - 多语种版", styles["Title"]))
    story.append(Spacer(1, 12))

    for r in results:
        lang_label = next(
            (l["label"] for l in LANGUAGES if l["code"] == r["lang"]), r["lang"]
        )
        story.append(
            Paragraph(f'<font color="#2563eb">{lang_label}</font>', styles["Heading3"])
        )
        for line in r["text"].split("\n"):
            story.append(Paragraph(line, styles["Normal"]))
        story.append(Spacer(1, 10))

    doc.build(story)
    buf.seek(0)

    from flask import Response

    return Response(
        buf.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={material_type}-multilingual.pdf"
        },
    )


@translate_bp.route("/api/export-image", methods=["POST"])
@login_required
@rate_limit("export")
def export_image():
    try:
        from flask import Response
        from app.image_export import generate_zip_of_cards, generate_card_image

        data = request.get_json()
        results = data.get("results", [])
        material_type = data.get("materialType", "")
        single = data.get("single", False)

        type_label = next(
            (t["label"] for t in MATERIAL_TYPES if t["id"] == material_type), ""
        )

        lang_label_map = {l["code"]: f"{l['flag']} {l['label']}" for l in LANGUAGES}

        if single and results:
            r = results[0]
            lang_label = lang_label_map.get(r["lang"], r["lang"])
            buf = generate_card_image(r["text"], r["lang"], type_label, lang_label)
            return Response(
                buf.getvalue(),
                mimetype="image/png",
                headers={
                    "Content-Disposition": f"attachment; filename={material_type}-{r['lang']}.png"
                },
            )

        buf = generate_zip_of_cards(results, type_label, lang_label_map)
        return Response(
            buf.getvalue(),
            mimetype="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={material_type}-cards.zip"
            },
        )
    except Exception as e:
        print(f"Image export error: {e}", file=sys.stderr)
        return jsonify({"error": "Image generation failed"}), 500


@translate_bp.route("/api/translate/generate-description", methods=["POST"])
@login_required
@rate_limit("generate_description", identifier_fn=lambda: session.get("user_id", "anon"))
def generate_description():
    from app.kv_client import redis_get
    from flask import session

    user_id = session["user_id"]

    # Load merchant profile
    raw = redis_get(f"profile:{user_id}")
    profile = {}
    if raw:
        try:
            profile = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass

    store_name = profile.get("store_name", "")
    category = profile.get("category", "")
    city = profile.get("city", "")
    desc = profile.get("description", "")
    address = profile.get("address", "")

    if not store_name:
        return jsonify({"error": "请先在控制台填写门店信息"}), 400

    prompt = (
        f"Write a 150-200 word English description for a TripAdvisor listing for a {category or 'restaurant/hotel'} in {city or 'China'}.\n\n"
        f"Name: {store_name}\n"
        f"Address: {address}\n"
        f"Chinese description: {desc}\n\n"
        "Rules:\n"
        "- Warm, inviting American English\n"
        "- Short paragraphs, easy to read\n"
        "- Highlight what makes it special\n"
        "- Include a sentence about location if relevant\n"
        "- No markdown, no bullet points — just a clean description\n"
        "- Output ONLY the description, nothing else"
    )

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return jsonify({"error": "API key not configured"}), 500

    try:
        req_body = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a travel copywriter for TripAdvisor."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 600,
        }).encode("utf-8")

        req = Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=req_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
        return jsonify({"description": body["choices"][0]["message"]["content"]})
    except URLError as e:
        try:
            from app.beta import log_error_to_kv
            log_error_to_kv("translate", "Description gen URLError", str(e.reason))
        except Exception:
            pass
        return jsonify({"error": f"生成失败：{str(e.reason)}"}), 500
    except Exception as e:
        try:
            from app.beta import log_error_to_kv
            log_error_to_kv("translate", "Description gen exception", str(e))
        except Exception:
            pass
        return jsonify({"error": f"生成失败：{str(e)}"}), 500
