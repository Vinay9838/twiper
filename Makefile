# Makefile for common developer tasks

SHELL := /usr/bin/env bash

.PHONY: backup deploy

# Run the backup that fetches posted.json from the deployed Fly app.
backup:
	@echo "Running backup..."
	@./scripts/fly_backup_posted.sh

# Run backup then deploy to Fly. Any arguments after -- are passed to `fly deploy`.
deploy: backup
	@echo "Deploying to Fly (app: twiper)..."
	@fly deploy --app twiper $(filter-out $@,$(MAKECMDGOALS))

# Allow passing extra args to `make deploy` like: `make deploy -- --remote-only`
%:
	@:
