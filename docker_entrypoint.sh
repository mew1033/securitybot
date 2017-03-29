#!/bin/bash
set -e


end=$((SECONDS + 120))

# Wait max of 2 minutes for database to come up
echo "Connecting to database $DB_HOST with user $DB_USER"
until mysql --user $DB_USER --password=$DB_PASS --host=$DB_HOST -e"quit" || [ $SECONDS -ge $end ]; do echo "Waiting for DB"; sleep 2; done;

# Check if database is initialized
echo "Connected, using database $DB_NAME"
if ! mysql --user $DB_USER --password=$DB_PASS --host=$DB_HOST -e"use $DB_NAME"; then
  echo "Creating database"
  mysql --user $DB_USER --password=$DB_PASS --host=$DB_HOST -e"create database $DB_NAME"
  echo "Populating database"
  exec python /securitybot/util/db_up.py
fi
echo "Database exists"

if [ "$1" = 'bot' ]; then
  echo "Starting bot"
  shift
  exec python /securitybot/main.py "$@"
elif [ "$1" = 'frontend' ]; then
  echo "Starting frontend"
  shift
  exec python /securitybot/frontend/securitybot_frontend.py "$@"
fi

exec "$@"
