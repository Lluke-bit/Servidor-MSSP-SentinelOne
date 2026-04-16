# S1 MSSP Pro Automation - Relatório de Consumo
# Autor: Lucas Borges
# Versão: 3.0 (Corrigida + Realtime + Sem agents/count)

import os
import csv
import requests
from dotenv import load_dotenv


class S1MSSPPro:

    def __init__(self):
        load_dotenv()

        self.base_url = os.getenv("S1_BASE_URL", "").rstrip("/")
        self.api_token = os.getenv("S1_API_TOKEN", "")

        if not self.base_url or not self.api_token:
            raise ValueError("Defina S1_BASE_URL e S1_API_TOKEN no .env")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"ApiToken {self.api_token}",
            "Content-Type": "application/json",
        })

        print(f"[INFO] Conectado: {self.base_url}")

    # =========================
    # GENERIC PAGINATION
    # =========================
    def _get_paginated(self, endpoint, params=None):
        results = []
        cursor = None

        while True:
            current_params = (params or {}).copy()
            if cursor:
                current_params["cursor"] = cursor

            url = f"{self.base_url}/web/api/v2.1/{endpoint}"

            try:
                response = self.session.get(url, params=current_params, timeout=30)
            except requests.RequestException as e:
                print(f"[ERRO] {endpoint}: {e}")
                break

            if response.status_code != 200:
                print(f"[ERRO] {endpoint}: {response.status_code}")
                break

            body = response.json()
            data = body.get("data", [])

            results.extend(data)

            cursor = body.get("pagination", {}).get("nextCursor")
            if not cursor:
                break

        return results

    # =========================
    # ACCOUNTS
    # =========================
    def get_accounts(self):
        print("[INFO] Coletando accounts...")
        return self._get_paginated("accounts")

    # =========================
    # SITES (COM INCLUDE)
    # =========================
    def get_sites(self, account_id):
        results = []
        cursor = None

        while True:
            params = {
                "accountIds": str(account_id),
                "state": "active",
                "include": "activeLicenses,sku,features,modules"
            }

            if cursor:
                params["cursor"] = cursor

            url = f"{self.base_url}/web/api/v2.1/sites"

            try:
                response = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as e:
                print(f"[ERRO] /sites: {e}")
                break

            if response.status_code != 200:
                print(f"[ERRO] /sites: {response.status_code}")
                break

            body = response.json()
            sites_list = body.get("data", {}).get("sites", [])

            results.extend(sites_list)

            cursor = body.get("pagination", {}).get("nextCursor")
            if not cursor:
                break

        return results

    # =========================
    # AGENTS
    # =========================
    def get_agents(self, site_id):
        return self._get_paginated("agents", {
            "siteIds": site_id,
            "isDecommissioned": False
        })

    # =========================
    # PROCESSAMENTO
    # =========================
    def extract_site_info(self, site):
        return {
            "site_name": site.get("name", "N/A"),
            "site_id": site.get("id"),
            "sku": (site.get("sku") or "").lower(),
            "active_licenses": site.get("activeLicenses", 0),
            "features": ",".join(site.get("features", [])) if site.get("features") else "",
            "modules": ",".join(site.get("modules", [])) if site.get("modules") else ""
        }

    def count_agents(self, agents):
        result = {"workstations": 0, "servers": 0}

        for a in agents:
            mt = (a.get("machineType") or "").lower()

            if mt in ["desktop", "laptop"]:
                result["workstations"] += 1
            elif mt == "server":
                result["servers"] += 1

        return result

    # =========================
    # PRINT REALTIME
    # =========================
    def print_site(self, acc_name, site_info, counts):
        print(f"\n[ACCOUNT] {acc_name}", flush=True)
        print(f"  └── [SITE] {site_info['site_name']}", flush=True)
        print(f"      ├── SKU: {site_info['sku']}", flush=True)
        print(f"      ├── Active Licenses: {site_info['active_licenses']}", flush=True)
        print(f"      ├── Workstations: {counts['workstations']}", flush=True)
        print(f"      ├── Servers: {counts['servers']}", flush=True)
        print(f"      ├── Features: {site_info['features'] or 'None'}", flush=True)
        print(f"      └── Modules: {site_info['modules'] or 'None'}", flush=True)

    # =========================
    # MAIN
    # =========================
    def run(self):
        accounts = self.get_accounts()

        report_rows = []

        for acc in accounts:
            acc_id = acc.get("id")
            acc_name = acc.get("name", "N/A")

            sites = self.get_sites(acc_id)

            for site in sites:
                site_info = self.extract_site_info(site)

                agents = self.get_agents(site_info["site_id"])

                if not agents:
                    continue

                counts = self.count_agents(agents)

                # PRINT REALTIME
                self.print_site(acc_name, site_info, counts)

                is_complete = "complete" in site_info["sku"]
                is_control = "control" in site_info["sku"]

                report_rows.append({
                    "ACCOUNT": acc_name,
                    "SITE": site_info["site_name"],
                    "SKU": site_info["sku"],
                    "ACTIVE_LICENSES": site_info["active_licenses"],
                    "FEATURES": site_info["features"],
                    "MODULES": site_info["modules"],

                    "Complete_Workstations": counts["workstations"] if is_complete else 0,
                    "Complete_Servers": counts["servers"] if is_complete else 0,
                    "Control_Workstations": counts["workstations"] if is_control else 0,
                    "Control_Servers": counts["servers"] if is_control else 0,
                })

        # EXPORT CSV
        if report_rows:
            with open("mssp_consumption_pro.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=report_rows[0].keys())
                writer.writeheader()
                writer.writerows(report_rows)

            print(f"\n[SUCESSO] CSV gerado ({len(report_rows)} linhas)")
        else:
            print("[AVISO] Nenhum dado coletado")


if __name__ == "__main__":
    app = S1MSSPPro()
    app.run()
