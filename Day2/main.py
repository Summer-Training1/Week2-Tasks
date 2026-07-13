import customtkinter as ctk
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
# threading lets the API call run in the background without freezing the window
import threading
# json lets us convert Gemini's text response into usable Python data
import json

# Load environment variables from the .env file
load_dotenv()

# Check if the API key exists before trying to use it
if not os.getenv("GEMINI_API_KEY"):
    print("Error: GEMINI_API_KEY not found. Check your .env file.")
    exit()

# Initialize the Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
status_label.pack(pady=(0, 10))

# RESULTS FRAME — the meal plan page with clickable cards
results_title = ctk.CTkLabel(results_frame, text="Your Meal Plan", font=("Arial", 22, "bold"))
results_title.pack(pady=20)

# Scrollable area to hold all the day/meal cards
cards_container = ctk.CTkScrollableFrame(results_frame, width=700, height=450)
cards_container.pack(pady=10)

back_button = ctk.CTkButton(results_frame, text="Back to Preferences")
back_button.pack(pady=10)


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
    # Immediately disable the button and show a loading message,
    # so the user gets instant feedback before the API call even starts
    generate_button.configure(state="disabled", text="Generating...")
    status_label.configure(text="Consulting AI Chef... Please wait.")

    # Run the actual API call on a separate thread so the window doesn't freeze while waiting
    thread = threading.Thread(target=fetch_meal_plan)
    thread.start()


def fetch_meal_plan():
    prompt = build_meal_plan_prompt()
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw_text = response.text.strip()
        # Safety net: strip ```json code fences in case Gemini adds them anyway
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            raw_text = raw_text.replace("json", "", 1).strip()
        # Convert the JSON text into an actual Python dictionary/list structure
        meal_plan_data = json.loads(raw_text)

    # Catch ANY failure (bad JSON, network error, etc.) so the app doesn't crash
    except Exception as e:
        meal_plan_data = None
        print(f"Error: {e}")

    # app.after(0, ...) hands the result back to the main thread to update the interface
    app.after(0, show_results_page, meal_plan_data)


def show_results_page(meal_plan_data):
    # Re-enable the button and clear the "please wait" message
    generate_button.configure(state="normal", text="Generate Meal Plan")
    status_label.configure(text="")

     # If the API call failed, show an error and stop here — don't try to build cards from nothing
    if meal_plan_data is None:
        status_label.configure(text="Something went wrong. Please try again.")
        return

    # Clear any old cards from a previous run
    for widget in cards_container.winfo_children():
        widget.destroy()

    # Loop through every day, then every meal within that day
    for day in meal_plan_data.get("days", []):
        day_number = day.get("day")

        day_heading = ctk.CTkLabel(
            cards_container,
            text=f"Day {day_number}",
            font=("Arial", 18, "bold")
        )
        day_heading.pack(pady=(15, 5), anchor="w")

        for meal in day.get("meals", []):
         # One card gets created per meal
            create_meal_card(meal)

    # Switch from input page to results page
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
    prompt = (
        f"Give me a detailed recipe for: {meal['name']}\n"
        f"Description: {meal['description']}\n\n"
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
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw_text = response.text.strip()

        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            raw_text = raw_text.replace("json", "", 1).strip()

        recipe_data = json.loads(raw_text)

    except Exception as e:
        recipe_data = None
        print(f"Error: {e}")

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

# Reverse of the page switch 
def go_back_to_preferences():
    results_frame.pack_forget()
    input_frame.pack(fill="both", expand=True)


# Attach button commands
generate_button.configure(command=generate_meal_plan_thread)
back_button.configure(command=go_back_to_preferences)

# Show the input page first
input_frame.pack(fill="both", expand=True)

app.mainloop()