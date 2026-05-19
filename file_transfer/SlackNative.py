import pyautogui
import time

# --- CONFIGURATION ---
CHANNEL_NAME = "general" 
FILE_PATH = r"C:\Users\YourName\Documents\test_file.pdf" 

print("Starting Slack automation in 3 seconds...")
time.sleep(3)

try:
    # 1-3. Open Slack and find channel (Same as before)
    pyautogui.press('win')
    time.sleep(1)
    pyautogui.write('Slack')
    time.sleep(1)
    pyautogui.press('enter')
    time.sleep(5) 

    pyautogui.hotkey('ctrl', 'k')
    time.sleep(1.5)
    pyautogui.write(CHANNEL_NAME)
    time.sleep(2)
    pyautogui.press('enter')
    time.sleep(2) 

    # 4-5. Open File Upload and Attach
    pyautogui.hotkey('ctrl', 'u')
    time.sleep(2.5) 
    pyautogui.write(FILE_PATH)
    time.sleep(1)
    pyautogui.press('enter')

    # --- NEW: DLP Popup Handling ---
    print("Checking for Cortex DLP popup...")
    time.sleep(2) # Give the Cortex agent time to scan and trigger the popup

    try:
        # Scans the screen for your cropped image. 'confidence=0.8' gives it a 20% margin of error.
        button_location = pyautogui.locateCenterOnScreen('confirm_button.png', confidence=0.8)
        
        if button_location is not None:
            print("DLP popup detected! Clicking the button...")
            pyautogui.click(button_location)
            time.sleep(1) # Wait for the popup to close
    except pyautogui.ImageNotFoundException:
        # This is the normal path if the file is safe and no popup appears
        print("No DLP popup detected. Proceeding normally.")
    # -------------------------------

    # 6. Send the message
    print("Sending file to channel...")
    time.sleep(2) 
    pyautogui.press('enter')

    print("Success! Workflow completed.")

except Exception as e:
    print(f"An error occurred: {e}")