from custom.waves_api import WavesDailyClient


def main() -> None:
    client = WavesDailyClient()
    resp = client.get_daily_info()
    print(resp)
    resp = client.sign_in()
    print(resp)
    client.close()


if __name__ == "__main__":
    main()
