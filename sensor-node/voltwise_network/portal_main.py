"""Run captive portal HTTP server (port 80). Used as subprocess by voltwise-network daemon."""
from voltwise_network.portal_app import run_portal

if __name__ == "__main__":
    run_portal()
