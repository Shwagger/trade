"""AI Demand Hunter - find people who already asked to pay for something.

The bet is simple: prospecting is exhausting because it starts from a blank
page. It stops being exhausting when a machine reads the public places where
buyers *write down their own problem*, throws away 90% of it, and hands back a
short list of requests that are worth ten minutes of a human's time.

What this package does, in order:

    fetch     public posts from free, read-only endpoints (no API key, no cost)
    qualify   score buyer intent 0-100 from explicit signals, not vibes
    extract   budget, deadline, category, how to answer
    prepare   a price and a first message, written for that exact post
    hand off  to a human, who reads it and decides whether to send it

What it deliberately does **not** do: send anything. No auto-reply, no mass DM,
no account automation. Every platform here forbids it, and it is spam. The
machine does the hunting; the human does the talking.

The second output matters as much as the leads: ``python -m hunter market``
counts what people actually asked for over the last N days. That is the market
telling you what to sell, instead of you guessing.
"""

__version__ = "0.1.0"

DEFAULT_WORKDIR = "state/hunter"
