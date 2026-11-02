"""Passively verify the historical durable cohort with its exact captured code."""
import json
from render_durable_mws import retained

if __name__=='__main__':
    print(json.dumps(retained(),sort_keys=True))
