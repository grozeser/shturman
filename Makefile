.PHONY: up down logs local-llm bot test eval seed e2e redteam

up:            ## Собрать и запустить стенд → http://localhost:8080
	docker compose up --build -d --wait

down:          ## Остановить стенд
	docker compose down

logs:          ## Логи приложения
	docker compose logs -f app

local-llm:     ## Стенд + своя LLM в Docker (Ollama, данные не уходят наружу; первый запуск качает ~2,5 ГБ)
	docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up --build -d --wait

bot:           ## Стенд + Telegram-бот (нужен TELEGRAM_BOT_TOKEN в .env)
	docker compose --profile telegram up --build -d

seed:          ## Демо-данные встроены в образ и генерируются детерминированно — отдельный сид не нужен
	@echo "Данные готовы: 62 направления, климат и синтетический инвентарь внутри образа"

eval:          ## Прогон эталонного набора запросов и отчёт для страницы «Метрики»
	docker compose exec app python -m app.eval

test:          ## Тесты бэкенда (локально, без Docker)
	cd backend && python -m pytest -q

e2e:           ## Сквозные тесты в браузере против запущенного стенда (make up); адрес — E2E_BASE_URL
	cd e2e && npm install --no-audit --no-fund && npx playwright install chromium && npx playwright test

redteam:       ## «Злые» запросы: опечатки, сленг, разговоры не о поездке — что агент понял и не упал ли
	cd backend && python ../scripts/redteam.py --only-flagged
