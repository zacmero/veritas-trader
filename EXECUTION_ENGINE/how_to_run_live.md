## Operational Mechanics (The Daemons)


**Q: Do I need to run the dynamic hedger in a while loop, or is it a daemon?**
The dynamic_hedger.py script already contains a while True: loop inside its Python code. Once you run it, it acts as a daemon and will run forever until you stop it (Ctrl+C).
Best Practice: Even though it loops internally, running it via a bash loop (while true; do python3 -m ...; sleep 5; done) is highly recommended for production. If the Alpaca API drops connection and crashes the Python script, the bash loop will automatically restart the daemon.


**Q: Can I run the dynamic hedger before the casino entry?**
Yes. This is actually the safest way to operate. If you start the hedger first, it will query Alpaca, see 0 options, print "No active options found. Waiting for Casino entry...", and go to sleep. The moment casino_entry.py successfully buys an option, the hedger will detect it on its next cycle and immediately begin hedging.
