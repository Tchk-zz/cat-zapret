import random
import time
from collections import Counter

from typing import Dict, List, Iterator, Tuple 


class _Balancer:
    def __init__(self):
        self.domains: List[str] = []
        self._dc_to_domain: Dict[int, str] = {}
        # (dc, domain) -> unix monotonic timestamp until which the domain is
        # temporarily skipped. Cloudflare can return HTTP 429 when a public
        # proxy domain is rate-limited; immediately retrying the same domains
        # for every Telegram connection only makes the limit worse.
        self._cooldown_until: Dict[Tuple[int, str], float] = {}
    
    def update_domains_list(self, domains_list: List[str]) -> None:
        if Counter(self.domains) == Counter(domains_list):
            return
        
        self.domains = domains_list[:]
        self._cooldown_until = {
            key: until for key, until in self._cooldown_until.items()
            if key[1] in self.domains and until > time.monotonic()
        }

        self._dc_to_domain = {
            dc_id: random.choice(self.domains)
            for dc_id in (1, 2, 3, 4, 5, 203)
        } if self.domains else {}

    def update_domain_for_dc(self, dc_id: int, domain: str) -> bool:
        if self._dc_to_domain.get(dc_id) == domain:
            return False
        
        self._dc_to_domain[dc_id] = domain
        return True

    def mark_domain_failed(self, dc_id: int, domain: str, cooldown: float) -> None:
        """Temporarily skip a CF proxy domain for a DC.

        This is the real mitigation for HTTP 429 spam: once Cloudflare says a
        public proxy hostname is rate-limited, stop hammering it for a while and
        let other domains / direct TCP fallback try instead.
        """
        if not domain or cooldown <= 0:
            return
        self._cooldown_until[(dc_id, domain)] = time.monotonic() + cooldown
        if self._dc_to_domain.get(dc_id) == domain:
            self._dc_to_domain.pop(dc_id, None)

    def is_domain_available(self, dc_id: int, domain: str) -> bool:
        until = self._cooldown_until.get((dc_id, domain), 0.0)
        if until <= time.monotonic():
            if until:
                self._cooldown_until.pop((dc_id, domain), None)
            return True
        return False

    def get_domains_for_dc(self, dc_id: int) -> Iterator[str]:
        current_domain = self._dc_to_domain.get(dc_id)
        yielded = set()
        if current_domain is not None and self.is_domain_available(dc_id, current_domain):
            yielded.add(current_domain)
            yield current_domain

        shuffled_domains = self.domains[:]
        random.shuffle(shuffled_domains)

        for domain in shuffled_domains:
            if domain in yielded:
                continue
            if not self.is_domain_available(dc_id, domain):
                continue
            yield domain

    def cooldown_count(self, dc_id: int) -> int:
        """Return how many configured domains are currently cooling down."""
        return sum(
            1 for domain in self.domains
            if not self.is_domain_available(dc_id, domain)
        )


balancer = _Balancer()
