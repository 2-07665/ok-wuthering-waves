if __name__ == '__main__':
    import custom.log_filter

    from config import config
    from ok import OK

    config = config
    ok = OK(config)
    ok.start()
