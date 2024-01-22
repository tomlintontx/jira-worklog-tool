# Start up
1. You will need to have a .env file created with all of the appropriate values
2. Python3 needs to be installed on your machine
3. Run `pip3 install -r requirements.txt`
4. To run the program `python3 web-server.py`
5. If deploying on a server, it's best to run it in the background `nohup python3 web-server.py $`
6. You'll also need to deploy the application as a slack app
7. Ensure you have slash command URLs for all of the routes
8. Setup the redirect URL in slack
9. Allow people to send messages to the app in slack under app home
