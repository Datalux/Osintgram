SHELL := /bin/bash

setup:

	@echo -e "\e[34m####### Setup for Osintgram #######\e[0m"
	@[ -d config ] || mkdir config || exit 1
	@echo -n "{}" > config/settings.json
	@read -p "Instagram Username: " uservar; \
	echo -n $$uservar > config/username.conf || exit 1
	@read -sp "Instagram Password: " passvar; \
	echo -n $$passvar > config/pw.conf || exit 1
	@echo ""
	@echo -e "\e[32mSetup Successful\e[0m"

run:

	@echo -e "\e[34m######## Building and Running Osintgram with Docker-compose ########\e[0m"
	@[ -d config ] || { echo -e "\e[31mConfig folder not found! Please run 'make setup' before running this command.\e[0m"; exit 1; }
	@echo -e "\e[34m[#] Killing old docker processes\e[0m"
	@docker-compose rm -fs || exit 1
	@echo -e "\e[34m[#] Building docker containers\e[0m"
	@docker-compose up --build -d || exit 1
	@echo -e "\e[32m[#] Osintgram Container is now Running!\e[0m"