from custom.waves_api import WavesDailyClient, read_api_daily_info


def main() -> None:
    client = WavesDailyClient()
    resp = client.get_daily_info()
    print(resp)
    print(read_api_daily_info(client))
    client.close()


if __name__ == "__main__":
    main()
