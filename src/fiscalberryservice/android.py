from time import sleep
import os
from jnius import autoclass

# -*- coding: utf-8 -*-

"""
Basic structure for an Android background service using Python.
This typically requires a framework like Kivy (with python-for-android)
or Chaquopy to bridge Python with the Android OS.
"""


# Using jnius (common with Kivy/python-for-android) to interact with Android APIs
try:
    # Example: Get access to the service context if running under PythonService
    # PythonService = autoclass('org.kivy.android.PythonService')
    # service = PythonService.mService
    pass
except ImportError:
    print("jnius not found. Android-specific features may not work.")
    autoclass = None
    service = None

def run_service_logic():
    """Contains the main logic for the background service."""
    print("Android Service: Starting background logic.")

    # Example: Retrieve an argument passed when starting the service
    # This environment variable is often set by the service starter (e.g., Kivy's PythonService)
    service_argument = os.environ.get('PYTHON_SERVICE_ARGUMENT', 'No argument provided')
    print(f"Android Service: Received argument: {service_argument}")

    # Main service loop
    counter = 0
    while True:
        print(f"Android Service: Running... Loop count: {counter}")

        # --- Add your background tasks here ---
        # Examples:
        # - Polling a server for updates
        # - Processing data in the background
        # - Interacting with hardware (requires specific permissions and APIs)
        # - Sending notifications (requires Android API calls via jnius/plyer)

        # Example: Show a Toast notification (requires context and jnius)
        # if autoclass and service:
        #     try:
        #         Toast = autoclass('android.widget.Toast')
        #         CharSequence = autoclass('java.lang.CharSequence')
        #         context = service.getApplicationContext()
        #         if context:
        #             def show_toast():
        #                 text = CharSequence(f"Service running {counter}")
        #                 toast = Toast.makeText(context, text, Toast.LENGTH_SHORT)
        #                 toast.show()
        #             # Toasts must be shown on the UI thread
        #             PythonActivity = autoclass('org.kivy.android.PythonActivity')
        #             PythonActivity.mActivity.runOnUiThread(show_toast)
        #     except Exception as e:
        #         print(f"Android Service: Error showing toast - {e}")

        # Sleep for a period before the next iteration
        sleep(15) # Sleep for 15 seconds
        counter += 1

        # Add conditions to stop the service if necessary,
        # although services are often designed to run until explicitly stopped.
        # For example:
        # if should_stop_service():
        #     print("Android Service: Stopping condition met.")
        #     break

    print("Android Service: Background logic finished.")

if __name__ == "__main__":
    # This block is executed when the script is run directly.
    # When launched as an Android service by the framework (e.g., Kivy),
    # the framework typically imports and runs this script, potentially
    # calling a specific function or just executing the module level code.
    # The `run_service_logic()` function contains the core tasks.
    run_service_logic()

# --- Notes on Deployment as an Android Service ---
#
# 1.  **Framework:** Use Kivy (with buildozer) or Chaquopy.
# 2.  **Configuration (Buildozer Example):**
#     In `buildozer.spec`, define the service:
#     ```
#     services = YourServiceName:./src/fiscalberryservice/android.py
#     ```
#     Replace `YourServiceName` and adjust the path.
# 3.  **Starting the Service:**
#     Start it from your main app (e.g., Kivy `main.py`) using Android Intents via jnius:
#     ```python
#     from jnius import autoclass
#     import os
#
#     PythonActivity = autoclass('org.kivy.android.PythonActivity')
#     activity = PythonActivity.mActivity
#     Intent = autoclass('android.content.Intent')
#
#     service_name = 'YourServiceName' # Must match buildozer.spec
#     service_class_name = f'{activity.getPackageName()}.Service{service_name}'
#
#     intent = Intent()
#     intent.setClassName(activity, service_class_name)
#
#     # Pass data to the service (optional)
#     argument = "Data for the service"
#     intent.putExtra('PYTHON_SERVICE_ARGUMENT', argument)
#     os.environ['PYTHON_SERVICE_ARGUMENT'] = argument # Set env var too
#
#     activity.startService(intent)
#     ```
# 4.  **Permissions:** Add necessary permissions to `buildozer.spec`:
#     ```
#     android.permissions = INTERNET, FOREGROUND_SERVICE, ...
#     ```
#     `FOREGROUND_SERVICE` is often required for long-running tasks on newer Android versions.
# 5.  **Foreground Service:** For long-running tasks, consider running as a foreground service
#     to prevent Android from killing it. This requires showing a persistent notification.
#     You'll need more jnius code to create the notification channel and notification itself.