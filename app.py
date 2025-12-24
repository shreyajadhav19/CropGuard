

import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests
from datetime import datetime
from flask import flash
from dotenv import load_dotenv
from openai import OpenAI #
import sys 
#from app import db, Diary

# Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)

# Database Configuration

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///D:/certificates/agriconnect.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --------------------- OPENROUTER CONFIGURATION ---------------------

# 1. Get API Key from environment (loaded from .env, must be OPENROUTER_KEY)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Set a free-tier model for testing. Switched from deepseek/deepseek-r1:free due to rate limiting.
OPENROUTER_MODEL = "mistralai/mistral-7b-instruct:free" 

# Initialize the OpenAI client for OpenRouter
openai_client = None
try:
    if not OPENROUTER_API_KEY:
        print("FATAL ERROR: OPENROUTER_KEY not found in environment variables.")
        
    else:
        openai_client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL
        )
        print(f"OpenRouter client successfully initialized for model: {OPENROUTER_MODEL}")
except Exception as e:
    print(f"ERROR: Could not initialize OpenRouter client. Details: {e}")
    openai_client = None

# --------------------- Database Models ---------------------

class MarketPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crop_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    market_name = db.Column(db.String(150), nullable=False)  # e.g. state or mandi/market
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    renter = db.Column(db.String(100), nullable=False)   # renamed owner → renter
    location = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    rented_date = db.Column(db.String(20), nullable=False)
    returned_date = db.Column(db.String(20), nullable=True)
    status=db.Column(db.String(20),nullable=True)

class LearningResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(200), nullable=False)

class Diary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=False)
    entry_time = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"<Diary {self.id}>"


# --------------------- ROUTES ---------------------
@app.route('/')
def intro():
    return render_template('base.html')

@app.route('/home')
def home():
    return render_template('index.html')


# ---- Market Price Tracker (API + DB) ----
# ---- Market Price Tracker (Using Agmarknet API) ----

# ---- Market Price Tracker (API + DB) ----
@app.route('/market', methods=['GET', 'POST'])
def market():
    api_key = os.getenv("AGRI_API_KEY")  # put your API key in env var, recommended
    latest = None
    error_msg = None

    if request.method == 'POST':
        crop_name = request.form.get('crop_name', '').strip()
        market_name = request.form.get('market_name', '').strip()  # region/state/mandi

        # Basic validation
        if not crop_name or not market_name:
            flash("Please select both crop and market/region.")
            return redirect(url_for('market'))

        # --- Call external API (replace with real endpoint & params) ---
        price_value = None
        try:
            if api_key:
               
                url = "https://api.example.com/prices"
                params = {"commodity": crop_name, "location": market_name, "apikey": api_key}
                resp = requests.get(url, params=params, timeout=8)
                resp.raise_for_status()
                data = resp.json()

                # --- parse response according to the API's structure ---
                price_value = None
                if isinstance(data, dict):
                    # try multiple common keys
                    price_value = data.get("price") or data.get("value") or data.get("last_price")
                    # if nested:
                    if price_value is None:
                        # e.g. { "data":[{ "price": 2300, "market": "Pune" }] }
                        if "data" in data and isinstance(data["data"], list) and len(data["data"])>0:
                            price_value = data["data"][0].get("price") or data["data"][0].get("value")

            # fallback: no api_key or api call failed -> generate a mock price (for testing)
            if price_value is None:
                # MOCK: generate a plausible price based on crop name (simple deterministic fallback)
                base = {
                    "wheat": 2200, "rice": 2800, "cotton": 6500,
                    "soybean": 4900, "sugarcane": 330
                }
                key = crop_name.lower()
                price_value = base.get(key, 1500) + (hash(market_name) % 400)  # deterministic tweak
        except Exception as e:
            # Log the error on console and fallback to mock price
            print("Market API error:", e)
            error_msg = "Live API request failed — showing fallback price."
            # fallback price as above
            base = {"wheat": 2200, "rice": 2800, "cotton": 6500, "soybean": 4900, "sugarcane": 330}
            key = crop_name.lower()
            price_value = base.get(key, 1500) + (hash(market_name) % 400)

        # --- Save to DB ---
        try:
            price_float = float(price_value)
        except Exception:
            price_float = None

        if price_float is not None:
            new_entry = MarketPrice(crop_name=crop_name, price=price_float, market_name=market_name, timestamp=datetime.utcnow())
            db.session.add(new_entry)
            db.session.commit()
            latest = new_entry
        else:
            error_msg = "Price not found for selected crop/market."

    # On GET (or after POST) show the most recent entries (latest first)
    history = MarketPrice.query.order_by(MarketPrice.timestamp.desc()).limit(50).all()
    return render_template('market.html', latest=latest, history=history, error_msg=error_msg)




# ---------------- SMART CROP PLANNER (LIVE WEATHER + AI) ----------------

@app.route('/crop_planner', methods=['GET', 'POST'])
def crop_planner():
    crop_suggestion = None
    weather_data = None
    error_message = None

    if request.method == "POST":
        city = request.form.get("city")

        # ----------- 1. GET WEATHER USING OPENWEATHER (FREE API) -----------
        WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

        if not WEATHER_API_KEY:
            return "❌ WEATHER_API_KEY missing in .env file", 500

        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
            response = requests.get(url)
            data = response.json()

            if data.get("cod") != 200:
                error_message = "City not found. Enter a valid city name."
            else:
                weather_data = {
                    "city": city,
                    "temp": data["main"]["temp"],
                    "humidity": data["main"]["humidity"],
                    "condition": data["weather"][0]["description"].title()
                }

                # ----------- 2. ASK OPENROUTER AI FOR CROP SUGGESTION -----------
                if openai_client is None:
                    crop_suggestion = "AI unavailable — check OpenRouter key."
                else:
                    prompt = (
                        f"Based on the following live weather data:\n"
                        f"Temperature: {weather_data['temp']}°C\n"
                        f"Humidity: {weather_data['humidity']}%\n"
                        f"Weather Condition: {weather_data['condition']}\n"
                        f"Suggest 3 best crops to grow in {city} right now. "
                        f"Give a short explanation for each crop in simple language."
                    )

                    ai_response = openai_client.chat.completions.create(
                        model=OPENROUTER_MODEL,
                        messages=[
                            {"role": "system", "content": "You are a crop recommendation expert."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=200
                    )

                    crop_suggestion = ai_response.choices[0].message.content

        except Exception as e:
            error_message = f"Something went wrong: {str(e)}"

    return render_template("crop_planner.html",
                           weather=weather_data,
                           suggestion=crop_suggestion,
                           error=error_message)

# ---- Equipment Sharing ----
# ---- Equipment Sharing ----
# --------------------- PREDEFINED EQUIPMENT ---------------------
PREDEFINED_EQUIPMENT = [
    "Tractor", "Rotavator", "Harvester", "Cultivator", "Plough",
    "Seed Drill", "Sprayer", "Thresher", "Power Tiller",
    "Water Pump", "Seeder", "Leveller", "Disc Harrow"
]


# --------------------- HELPER FUNCTIONS ---------------------
def get_unique_equipment_from_db():
    """Fetch unique equipment names from DB."""
    items = db.session.query(Equipment.name).distinct().all()
    return [i[0] for i in items]


def get_available_equipment_names():
    """
    Show equipment in dropdown ONLY IF:
    - rented_date is NULL (never rented)
    - OR returned_date is NOT NULL (previously rented but returned)
    """
    available_items = Equipment.query.filter(
        (Equipment.rented_date.is_(None)) |
        (Equipment.returned_date.isnot(None))
    ).all()

    return [item.name for item in available_items]


def merge_equipment_lists():
    """Combine predefined + DB + only available equipment."""
    all_items = set(PREDEFINED_EQUIPMENT + get_unique_equipment_from_db())
    unavailable_items = get_unavailable_equipment_names()
    # Remove rented equipment
    final_list = [item for item in all_items if item not in unavailable_items]
    return sorted(final_list)


def get_unavailable_equipment_names():
    """Returns equipment currently rented (not returned)."""
    items = Equipment.query.filter(
        Equipment.rented_date.isnot(None),
        Equipment.returned_date.is_(None)
    ).all()
    return [item.name for item in items]


# --------------------- ROUTES ---------------------
@app.route("/equipment", methods=["GET"])
def equipment():

    all_equipment = Equipment.query.all()
    equipment_list = []

    for item in all_equipment:
        if item.rented_date and not item.returned_date:
            status = "Rented"
        else:
            status = "Available"

        equipment_list.append({
            "id": item.id,
            "name": item.name,
            "renter": item.renter,
            "location": item.location,
            "price": item.price,
            "rented_date": item.rented_date if item.rented_date else "None",
            "returned_date": item.returned_date if item.returned_date else "-",
            "status": status
        })

    # FINAL DROPDOWN LIST = predefined + DB items - unavailable ones
    dropdown_items = merge_equipment_lists()

    return render_template("equipment.html",
                           equipment_data=equipment_list,
                           equipment_list=dropdown_items)


@app.route("/equipment/add", methods=["POST"])
def add_equipment():
    name = request.form['name'].strip()
    renter = request.form['renter'].strip()
    location = request.form['location'].strip()
    price = request.form['price'].strip()
    rented_date = request.form["rented_date"].strip()
    returned_date = request.form["returned_date"].strip()

    if not name or not renter or not location or not price:
        return "Please fill all required fields!", 400

    new_item = Equipment(
    name=name,
    renter=renter,
    location=location,
    price=price,
    rented_date=rented_date if rented_date else None,
    returned_date=returned_date if returned_date else None,
    status="Rented" if rented_date and not returned_date else "Available"
)


    db.session.add(new_item)
    db.session.commit()

    return redirect("/equipment")
@app.route("/equipment/return/<int:item_id>", methods=["POST"])
def mark_returned(item_id):
    returned_date = request.form.get("returned_date")

    if not returned_date:
        return "Returned date required!", 400

    item = Equipment.query.get(item_id)
    if not item:
        return "Item not found!", 404

    item.returned_date = returned_date
    item.status = "Available"

    db.session.commit()
    return redirect("/equipment")



# ------------
# ===========================================================


# ------------
# ===========================================================

#learning hub
@app.route('/learning', methods=['GET', 'POST'])
def learning():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        link = request.form['link']
        new_resource = LearningResource(title=title, description=description, link=link)
        db.session.add(new_resource)
        db.session.commit()
        return redirect(url_for('learning'))
    resources = LearningResource.query.all()
    return render_template('learning.html', resources=resources)



# ---- AI Chatbot (OpenRouter API) ----

@app.route('/chatbot_api', methods=['GET'])
def chatbot_page():
    # Placeholder for rendering the frontend chatbot page
    return render_template('chatbot.html')


@app.route('/chatbot_api', methods=['POST'])
def chatbot_api():
    user_message = request.json.get('message', '')

    # Check for OpenRouter client readiness
    if openai_client is None:
        return jsonify({"reply": "❌ Configuration Error: OpenRouter key not set or client initialization failed."})

    # System instruction for the model
    system_instruction = (
        "You are AgriSmart, expert in Indian crops, soil nutrients, "
        "diseases, fertilizers and irrigation. Reply in simple, short language."
    )

    # Message structure for the OpenAI client
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_message}
    ]

    try:
        # Make the request to OpenRouter using the OpenAI client
        response = openai_client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=200 # Limiting tokens for concise replies
        )

        # Extract the generated text
        bot_reply = response.choices[0].message.content
        
        # OpenRouter responses may contain usage information, but standard citations are not provided 
        # like they are in the Google Search Grounding for Gemini.

        return jsonify({"reply": bot_reply})

    except Exception as e:
        print(f"❌ OpenRouter API Request Error: {e}")
        # Return a user-friendly error if the network or API request failed
        return jsonify({
            "reply": f"Sorry 🌾, the AI service is unreachable or the model is unavailable via OpenRouter. Details: {str(e)}",
            "tip": "Check your OpenRouter dashboard for quota/usage information."
        })

##########################
@app.route("/diary")
def diary():
    entries = Diary.query.order_by(Diary.id.desc()).all()
    return render_template("diary.html", entries=entries)


@app.route("/save_diary", methods=["POST"])
def save_diary():
    category = request.form.get("category")
    details = request.form.get("details")
    entry_time = request.form.get("entry_time")

    new_entry = Diary(
        category=category,
        details=details,
        entry_time=entry_time
    )

    db.session.add(new_entry)
    db.session.commit()

    return redirect(url_for("diary"))
@app.route('/diary_search', methods=['GET', 'POST'])
def diary_search():
    entries = None

    if request.method == "POST":
        search_date = request.form['search_date']  # YYYY-MM-DD format

        # Filter using SQLAlchemy
        entries = Diary.query.filter(
            Diary.entry_time.like(f"{search_date}%")
        ).all()

    return render_template("diary_search.html", entries=entries)
# --------------------- RUN APP ---------------------
if __name__ == '__main__':
    with app.app_context():
        # Create database tables if they don't exist
        db.create_all()
    app.run(debug=True)






