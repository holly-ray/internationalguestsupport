import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__, template_folder="templates")

    app.secret_key = os.getenv("SESSION_SECRET", os.urandom(24).hex())
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    from app.translate import translate_bp
    from app.auth import auth_bp
    from app.merchant import merchant_bp
    from app.gmb import gmb_bp
    from app.payment import payment_bp
    from app.psb import psb_bp
    from app.beta import beta_bp
    from app.guide import guide_bp

    app.register_blueprint(translate_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(merchant_bp)
    app.register_blueprint(gmb_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(psb_bp)
    app.register_blueprint(beta_bp)
    app.register_blueprint(guide_bp)

    @app.route("/")
    def index():
        from flask import render_template

        return render_template("index.html")

    @app.route("/dashboard")
    def dashboard():
        from flask import render_template

        return render_template("dashboard.html")

    @app.route("/tripadvisor")
    def tripadvisor_guide():
        from flask import render_template

        return render_template("tripadvisor_guide.html")

    @app.route("/psb")
    def psb_guide():
        from flask import render_template

        return render_template("psb_guide.html")

    @app.route("/gmb/guide")
    def gmb_guide():
        from flask import render_template

        return render_template("gmb_guide.html")

    @app.route("/health")
    def health():
        from flask import redirect

        return redirect("/api/health")

    return app
