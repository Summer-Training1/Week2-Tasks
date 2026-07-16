import customtkinter as ctk
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
# threading lets the API call run in the background without freezing the window
import threading
# json lets us convert Gemini's text response into usable Python data
import json
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from textwrap import wrap

# Load environment variables from the .env file
load_dotenv()

# Check if the API key exists before trying to use it
if not os.getenv("GEMINI_API_KEY"):
    print("Error: GEMINI_API_KEY not found. Check your .env file.")
    exit()

# Initialize the Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# Keeps track of the most recently generated meal plan, so we can return to it from a recipe
current_meal_plan = None

# Set dark mode + blue theme, then create the main window (800x700 pixels)
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("MealMate AI")
app.geometry("800x700")


# Create two frames(pages): one for input, one for results
input_frame = ctk.CTkFrame(app, fg_color="transparent")
results_frame = ctk.CTkFrame(app, fg_color="transparent")

# INPUT FRAME — everything below is parented to input_frame

# Title label
title_label = ctk.CTkLabel(input_frame, text="MealMate AI", font=("Arial", 24, "bold"))
title_label.pack(pady=20)

# Fitness goal dropdown
fitness_goal_label = ctk.CTkLabel(input_frame, text="Fitness Goal:")
fitness_goal_label.pack(pady=(10, 0))
fitness_goal_dropdown = ctk.CTkOptionMenu(input_frame, values=["Muscle Gain", "Weight Loss", "Maintenance"])
fitness_goal_dropdown.pack(pady=5)

# Height slider
height_label = ctk.CTkLabel(input_frame, text="Height: 170 cm")
height_label.pack(pady=(10, 0))

def update_height_label(value):
    height_label.configure(text=f"Height: {int(value)} cm")

height_slider = ctk.CTkSlider(input_frame, from_=140, to=220, command=update_height_label)
height_slider.pack(pady=5)
height_slider.set(170)

# Weight slider
weight_label = ctk.CTkLabel(input_frame, text="Weight: 70 kg")
weight_label.pack(pady=(10, 0))

def update_weight_label(value):
    weight_label.configure(text=f"Weight: {int(value)} kg")

weight_slider = ctk.CTkSlider(input_frame, from_=40, to=180, command=update_weight_label)
weight_slider.pack(pady=5)
weight_slider.set(70)

# Dietary preference dropdown
diet_label = ctk.CTkLabel(input_frame, text="Dietary Preference:")
diet_label.pack(pady=(10, 0))
diet_dropdown = ctk.CTkOptionMenu(input_frame, values=["None", "High Protein", "Vegetarian", "Vegan", "Keto", "Low Carb"])
diet_dropdown.pack(pady=5)

# Number of days input
days_label = ctk.CTkLabel(input_frame, text="Number of Days (1-7):")
days_label.pack(pady=(10, 0))
days_entry = ctk.CTkEntry(input_frame, placeholder_text="e.g. 3")
days_entry.pack(pady=5)

# Ingredients textbox
ingredients_label = ctk.CTkLabel(input_frame, text="Available Ingredients (optional):")
ingredients_label.pack(pady=(10, 0))
ingredients_textbox = ctk.CTkTextbox(input_frame, height=80, width=400)
ingredients_textbox.pack(pady=5)

# Generate Meal Plan button
generate_button = ctk.CTkButton(input_frame, text="Generate Meal Plan")
generate_button.pack(pady=20)

# Status label (replaces the old output_textbox for showing "loading"/error messages)
status_label = ctk.CTkLabel(input_frame, text="")
# Note: not packed here — it only appears when needed, controlled inside generate_meal_plan_thread()
view_old_plan_button = ctk.CTkButton(input_frame, text="View Current Plan")
status_label.pack(pady=(0, 10))

# RESULTS FRAME — the meal plan page with clickable cards
results_title = ctk.CTkLabel(results_frame, text="Your Meal Plan", font=("Arial", 22, "bold"))
results_title.pack(pady=20)

# Scrollable area to hold all the day/meal cards
cards_container = ctk.CTkScrollableFrame(results_frame, width=700, height=450)
cards_container.pack(pady=10)

back_button = ctk.CTkButton(results_frame, text="Back to Preferences")
back_button.pack(pady=10)

save_plan_txt_button = ctk.CTkButton(results_frame, text="Save as TXT")
save_plan_txt_button.pack(pady=5)

save_plan_pdf_button = ctk.CTkButton(results_frame, text="Save as PDF")
save_plan_pdf_button.pack(pady=5)


# LOGIC

def build_meal_plan_prompt():
    # Pull the current value out of each input widget and use .get() to retrive the value 
    fitness_goal = fitness_goal_dropdown.get()
    diet = diet_dropdown.get()
    days = days_entry.get()
    ingredients = ingredients_textbox.get("1.0", "end").strip()
    height = int(height_slider.get())
    weight = int(weight_slider.get())
    
    #based in your values fill the prompt
    prompt = (
        f"Create a {days}-day personalized meal plan.\n"
        f"Fitness goal: {fitness_goal}\n"
        f"Dietary preference: {diet}\n"
        f"User height: {height} cm, weight: {weight} kg\n"
    )

    # Only add the ingredients line if the user actually typed something
    if ingredients:
        prompt += f"Available ingredients to prioritize: {ingredients}\n"

    # Force Gemini to reply with structured JSON instead of free text —
    # this is what lets us loop through the data and build clickable cards later
    prompt += (
        "Respond ONLY with valid JSON, no extra text, no markdown formatting, "
        "in exactly this structure:\n"
        "{\n"
        '  "days": [\n'
        "    {\n"
        '      "day": 1,\n'
        '      "meals": [\n'
        '        {"type": "Breakfast", "name": "...", "description": "..."},\n'
        '        {"type": "Lunch", "name": "...", "description": "..."},\n'
        '        {"type": "Dinner", "name": "...", "description": "..."}\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    return prompt

def generate_meal_plan_thread():
    days = days_entry.get().strip()

    if not days.isdigit() or not (1 <= int(days) <= 7):
        status_label.configure(text="Please enter a number of days between 1 and 7.")
        return

    if current_meal_plan is not None and generate_button.cget("text") != "Confirm? This replaces your plan":
        generate_button.configure(text="Confirm? This replaces your plan")
        status_label.configure(text="You have an existing meal plan.")
        view_old_plan_button.pack(pady=(0, 10))
        return

    view_old_plan_button.pack_forget()
    start_meal_plan_generation()


def start_meal_plan_generation():
    generate_button.configure(state="disabled", text="Generating...")
    status_label.configure(text="Consulting AI Chef... Please wait.")

    thread = threading.Thread(target=fetch_meal_plan)
    thread.start()


def view_old_plan():
    if current_meal_plan:
        display_meal_plan_cards(current_meal_plan)
        input_frame.pack_forget()
        results_frame.pack(fill="both", expand=True)


def call_gemini_for_json(prompt):
    """
    Sends a prompt to Gemini and returns the parsed JSON response.
    Returns None if the call fails or the response isn't valid JSON.
    """
    try:
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt
        )
        raw_text = response.text.strip()

        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            raw_text = raw_text.replace("json", "", 1).strip()

        return json.loads(raw_text)

    except Exception as e:
        print(f"Error: {e}")
        return None
    
    
def fetch_meal_plan():
    prompt = build_meal_plan_prompt()
    meal_plan_data = call_gemini_for_json(prompt)
    app.after(0, show_results_page, meal_plan_data)


def display_meal_plan_cards(meal_plan_data):
    for widget in cards_container.winfo_children():
        widget.destroy()

    for day in meal_plan_data.get("days", []):
        day_number = day.get("day")

        day_heading = ctk.CTkLabel(
            cards_container,
            text=f"Day {day_number}",
            font=("Arial", 18, "bold")
        )
        day_heading.pack(pady=(15, 5), anchor="w")

        for meal in day.get("meals", []):
            create_meal_card(meal)

def show_results_page(meal_plan_data):
    # Re-enable the button and clear the "please wait" message
    generate_button.configure(state="normal", text="Generate Meal Plan")
    status_label.configure(text="")

     # If the API call failed, show an error and stop here — don't try to build cards from nothing
    if meal_plan_data is None:
        status_label.configure(text="Something went wrong. Please try again.")
        return
    
    global current_meal_plan
    current_meal_plan = meal_plan_data

    display_meal_plan_cards(meal_plan_data)

    input_frame.pack_forget()
    results_frame.pack(fill="both", expand=True)


def create_meal_card(meal):
    card = ctk.CTkButton(
        cards_container,
        text=f"{meal['type']}: {meal['name']}",
        anchor="w",
        height=40,
        command=lambda m=meal: on_meal_card_click(m)
    )
    card.pack(pady=4, fill="x")


# Same pattern as generate_meal_plan_thread(): show loading state immediately,
# then fetch the real data in the background
def on_meal_card_click(meal):
    show_recipe_loading(meal)
    thread = threading.Thread(target=fetch_recipe, args=(meal,))
    thread.start()

# Clear the meal cards and replace them with a temporary loading message
def show_recipe_loading(meal):
    for widget in cards_container.winfo_children():
        widget.destroy()

    loading_label = ctk.CTkLabel(
        cards_container,
        text=f"Getting the recipe for {meal['name']}...",
        font=("Arial", 16)
    )
    loading_label.pack(pady=20)

# Same JSON-structured-prompt approach as the meal plan,
# but requesting recipe-specific fields for just this one meal
def build_recipe_prompt(meal):
    diet = diet_dropdown.get()

    prompt = (
        f"Give me a detailed recipe for: {meal['name']}\n"
        f"Description: {meal['description']}\n"
        f"This recipe must follow this dietary preference: {diet}\n\n"
        "Respond ONLY with valid JSON, no extra text, no markdown formatting, "
        "in exactly this structure:\n"
        "{\n"
        '  "ingredients": ["...", "..."],\n'
        '  "instructions": ["...", "..."],\n'
        '  "cooking_time": "...",\n'
        '  "calories": "..."\n'
        "}"
    )
    return prompt


# Identical structure to fetch_meal_plan() — call Gemini, clean the response,
# parse the JSON, catch errors, then hand off to the main thread
def fetch_recipe(meal):
    prompt = build_recipe_prompt(meal)
    recipe_data = call_gemini_for_json(prompt)
    app.after(0, show_recipe_page, meal, recipe_data)


def show_recipe_page(meal, recipe_data):
    for widget in cards_container.winfo_children():
        widget.destroy()

    if recipe_data is None:
        error_label = ctk.CTkLabel(cards_container, text="Failed to load recipe. Try again.")
        error_label.pack(pady=20)
        return

    name_label = ctk.CTkLabel(cards_container, text=meal["name"], font=("Arial", 20, "bold"))
    name_label.pack(pady=(10, 5), anchor="w")

 # .get(key, 'N/A') safely handles a missing field instead of crashing
 # if Gemini's response happens to skip cooking_time or calories
    info_label = ctk.CTkLabel(
        cards_container,
        text=f"⏱ {recipe_data.get('cooking_time', 'N/A')}   |   🔥 {recipe_data.get('calories', 'N/A')}"
    )
    info_label.pack(pady=(0, 15), anchor="w")

    ingredients_heading = ctk.CTkLabel(cards_container, text="Ingredients:", font=("Arial", 16, "bold"))
    ingredients_heading.pack(pady=(10, 5), anchor="w")
    
    # One label per ingredient, prefixed with a bullet point
    for ingredient in recipe_data.get("ingredients", []):
        item = ctk.CTkLabel(cards_container, text=f"• {ingredient}", anchor="w", justify="left")
        item.pack(pady=2, anchor="w", fill="x")

    instructions_heading = ctk.CTkLabel(cards_container, text="Instructions:", font=("Arial", 16, "bold"))
    instructions_heading.pack(pady=(15, 5), anchor="w")

    for index, step in enumerate(recipe_data.get("instructions", []), start=1):
        step_label = ctk.CTkLabel(cards_container, text=f"{index}. {step}", anchor="w", justify="left", wraplength=650)
        step_label.pack(pady=4, anchor="w", fill="x")
        
    back_to_plan_button = ctk.CTkButton(
        cards_container,
        text="← Back to Meal Plan",
        command=go_back_to_meal_plan
    )
    back_to_plan_button.pack(pady=20)


# Returns to the previously saved meal plan cards, instead of the input page
def go_back_to_meal_plan():
    if current_meal_plan:
        display_meal_plan_cards(current_meal_plan)


# Reverse of the page switch 
def go_back_to_preferences():
    results_frame.pack_forget()
    input_frame.pack(fill="both", expand=True)


def meal_plan_to_text(meal_plan_data):
    lines = []
    for day in meal_plan_data.get("days", []):
        lines.append(f"Day {day.get('day')}")
        for meal in day.get("meals", []):
            lines.append(f"  {meal['type']}: {meal['name']}")
            lines.append(f"    {meal['description']}")
        lines.append("")
    return "\n".join(lines)

def save_as_txt(text, filename):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)
    status_label.configure(text=f"Saved as {filename}")


def save_as_pdf(text, filename):
    pdf = canvas.Canvas(filename, pagesize=A4)
    pdf.setFont("Helvetica", 11)

    lines = wrap(text, width=90)
    y = 800
    for line in lines:
        if y < 50:
            pdf.showPage()
            pdf.setFont("Helvetica", 11)
            y = 800
        pdf.drawString(50, y, line)
        y -= 20

    pdf.save()
    status_label.configure(text=f"Saved as {filename}")

# Attach button commands
generate_button.configure(command=generate_meal_plan_thread)
back_button.configure(command=go_back_to_preferences)
view_old_plan_button.configure(command=view_old_plan)
save_plan_txt_button.configure(command=lambda: save_as_txt(meal_plan_to_text(current_meal_plan), "meal_plan.txt"))
save_plan_pdf_button.configure(command=lambda: save_as_pdf(meal_plan_to_text(current_meal_plan), "meal_plan.pdf"))

# Show the input page first
input_frame.pack(fill="both", expand=True)

app.mainloop()