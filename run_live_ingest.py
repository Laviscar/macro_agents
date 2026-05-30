from pipelines.live_ingest import main
from utils.dotenv import load_dotenv


if __name__ == "__main__":
    load_dotenv()  # populate os.environ from .env (e.g. FINNHUB_API_KEY)
    main()
