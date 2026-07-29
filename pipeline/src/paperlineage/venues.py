"""対象会議・ジャーナルの定義。

Semantic Scholar の正規化 venue 名を使う。OpenAlex は ACM 会議論文の venue 情報が
欠落しているため(実測: CHI 2019 論文の primary_location.source が null)、
コーパスの「どの会議か」の判定には使えない。詳細は docs/data-sources.md。

s2_name は probe_venues.py で実測した値(2026-07-29 時点)。
total は同時点の bulk search 件数で、参考値。

注意: bulk search の `venue` パラメータは**カンマ区切りリスト**として解釈されるため、
venue 名に含まれるコンマで分割されて 0 件になる。`search_venue()` でコンマを除去する。
(実測: TEI の正式名にコンマが2個あり、そのままでは total=0、除去で 1995 件)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Venue:
    key: str  # 内部で使う短い ID
    s2_name: str  # Semantic Scholar の正規化 venue 名(実測値)
    label: str  # 表示用
    approx_total: int  # 2026-07-29 時点の bulk search 件数(参考)

    @property
    def search_venue(self) -> str:
        """bulk search に渡す形。コンマはリスト区切りとして解釈されるので除去する。"""
        return self.s2_name.replace(",", "")


VENUES: list[Venue] = [
    Venue("chi", "International Conference on Human Factors in Computing Systems", "CHI", 15435),
    Venue("pacmhci", "Proc. ACM Hum. Comput. Interact.", "PACM HCI", 3699),
    Venue("uist", "ACM Symposium on User Interface Software and Technology", "UIST", 3261),
    Venue("dis", "Conference on Designing Interactive Systems", "DIS", 2441),
    Venue("assets", "International ACM SIGACCESS Conference on Computers and Accessibility", "ASSETS", 2198),
    Venue("iui", "International Conference on Intelligent User Interfaces", "IUI", 2108),
    Venue("cscw", "Conference on Computer Supported Cooperative Work", "CSCW", 2019),
    Venue("tei", "International Conference on Tangible, Embedded, and Embodied Interaction", "TEI", 1995),
    Venue("imwut", "Proceedings of the ACM on Interactive Mobile Wearable and Ubiquitous Technologies", "IMWUT", 1861),
    Venue("ubicomp", "Ubiquitous Computing", "UbiComp", 1710),
    Venue("chiplay", "ACM SIGCHI Annual Symposium on Computer-Human Interaction in Play", "CHI PLAY", 1240),
    Venue("mobilehci", "International Conference on Human-Computer Interaction with Mobile Devices and Services", "MobileHCI", 937),
    Venue("tochi", "ACM Trans. Comput. Hum. Interact.", "TOCHI", 760),
]

VENUES_BY_KEY = {v.key: v for v in VENUES}

# 注記:
# - CSCW は 2017 以降 PACM HCI に移行しているため、`cscw` と `pacmhci` の両方が必要。
#   PACM HCI には EICS / ISS / CHI PLAY も含まれるので、CSCW だけを厳密に取り出したい場合は
#   別途 issue 単位の判別が要る。今は「HCI コーパス」としてまとめて入れる。
# - UbiComp / IMWUT も同様に 2017 前後で分割されている。
