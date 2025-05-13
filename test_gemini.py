import os
import google.generativeai as genai

# Replace with your actual API key for testing
API_KEY = "AIzaSyCcLig-l5OueKkXgyFh1PF_9wqudTWWKeo"

def test_gemini_connection():
    try:
        print("Configuring Gemini API...")
        genai.configure(api_key=API_KEY)

        print("Trying model: gemini-1.5-flash-latest")
        model = genai.GenerativeModel("gemini-1.5-flash-latest")
        response = model.generate_content("Hello, testing Gemini API connection")
        print("SUCCESS with gemini-1.5-flash-latest!")
        print(f"Response: {response.text}")
        return True
    except Exception as e:
        print(f"Gemini test failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting Gemini API test...")
    success = test_gemini_connection()
    print(f"Test {'succeeded' if success else 'failed'}")
