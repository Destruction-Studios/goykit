import time

import pyautogui
import pytesseract
from PIL import ImageOps
from pynput import mouse

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def waitForClick(pr):
    print(pr)
    result = {}

    def onClick(x, y, button, pressed):
        if pressed:
            result["pos"] = (x,y)
            return False
    
    with mouse.Listener(on_click=onClick) as listener:
        listener.join()

    print(f"    got {result['pos']}")
    time.sleep(0.3)
    return result["pos"]

def defineRegion(name):
    x1, y1 = waitForClick(f"[{name}] Click the TOP-LEFT corner...")
    x2, y2 = waitForClick(f"[{name}] Click the BOTTOM-RIGHT corner...")

    left, top = min(x1, x2), min(y1, y2)
    return (left, top, abs(x2-x1), abs(y2-y1))

def readText(region):
    img = pyautogui.screenshot(region=region)
    img = ImageOps.grayscale(img)
    img = img.resize((img.width*2, img.height*2))

    return pytesseract.image_to_string(img, config="--psm 7").strip().lower()

def main():
    word_region = defineRegion("Latin Word")
    answer_region = defineRegion("Answers")

    print(f"\nWords:    {word_region}")
    print(f"\nAnswers:    {answer_region}")
    print("\n Watching for words... (CTRL+C TO STOP)\n")

    last = None
    while True:
        word = readText(word_region)
        if word and word != last:
            print(f"\n\nDetected: {word}")
            last = word
        time.sleep(.2)


if __name__ == "__main__":
    main()