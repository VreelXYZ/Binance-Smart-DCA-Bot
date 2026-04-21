import subprocess
import time
import sys

def main():
    print("🚀 Starting Hammer ecosystem: Scanner + Aggressor Bot")
    
    # Start scanner and bot using the current Python executable
    scanner_process = subprocess.Popen([sys.executable, "scanner.py"])
    hammer_process = subprocess.Popen([sys.executable, "bot_hammer.py"])
    
    try:
        # Keep the main script alive to listen for Ctrl+C
        while True:
            time.sleep(1)
            
            # Optional: check if both processes died on their own
            if scanner_process.poll() is not None and hammer_process.poll() is not None:
                print("Both processes have stopped.")
                break
                
    except KeyboardInterrupt:
        print("\n🛑 Shutting down Hammer ecosystem...")
        # Gracefully terminate both if Ctrl+C is pressed
        scanner_process.terminate()
        hammer_process.terminate()
        scanner_process.wait()
        hammer_process.wait()
        print("Shutdown complete.")

if __name__ == "__main__":
    main()
