from PIL import Image
import sys
import os

def generate_icons():
    try:
        if not os.path.exists('central-dashboard/logo.png'):
            print("Error: logo.png not found")
            return

        img = Image.open('central-dashboard/logo.png')
        
        # Windows ICO
        img.save('central-dashboard/icon.ico', format='ICO', sizes=[(256, 256)])
        
        # Mac ICNS
        img.save('central-dashboard/icon.icns', format='ICNS', sizes=[(256, 256)])
        
        print("Icons generated successfully.")
    except Exception as e:
        print(f"Icon generation failed: {e}")

if __name__ == "__main__":
    generate_icons()
