@echo off
CALL conda activate rasa-bot
rasa run --enable-api --cors "*" --endpoints endpoints.yml
pause
