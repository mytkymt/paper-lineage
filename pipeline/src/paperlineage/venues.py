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
    # その venue の代表論文の DOI。probe_venues.py が s2_name の実測に使う。
    # 実測済みなら None でよい(HCI 13 venue は実測済みのため削除済み)。
    probe_doi: str | None = None
    # 年内での**おおよその開催月**。レイアウトが年内の x 方向の並びに使う
    # (地図を左から右に読むと、その年の学会が開かれた順になる)。
    # 年によって前後するので概略で十分。常時刊行のジャーナルは暦月を持たないので、
    # 関連する会議の時期(IMWUT→UbiComp、TOG→SIGGRAPH)か年半ばに置く。
    month: float = 6.0

    @property
    def search_venue(self) -> str:
        """bulk search に渡す形。コンマはリスト区切りとして解釈されるので除去する。"""
        return self.s2_name.replace(",", "")


VENUES: list[Venue] = [
    Venue("chi", "International Conference on Human Factors in Computing Systems", "CHI", 15435, month=5),
    Venue("pacmhci", "Proc. ACM Hum. Comput. Interact.", "PACM HCI", 3699, month=11.5),
    Venue("uist", "ACM Symposium on User Interface Software and Technology", "UIST", 3261, month=10.5),
    Venue("dis", "Conference on Designing Interactive Systems", "DIS", 2441, month=7),
    Venue("assets", "International ACM SIGACCESS Conference on Computers and Accessibility", "ASSETS", 2198, month=10),
    Venue("iui", "International Conference on Intelligent User Interfaces", "IUI", 2108, month=3),
    Venue("cscw", "Conference on Computer Supported Cooperative Work", "CSCW", 2019, month=11.2),
    Venue("tei", "International Conference on Tangible, Embedded, and Embodied Interaction", "TEI", 1995, month=2),
    Venue("imwut", "Proceedings of the ACM on Interactive Mobile Wearable and Ubiquitous Technologies", "IMWUT", 1861, month=8.5),
    Venue("ubicomp", "Ubiquitous Computing", "UbiComp", 1710, month=9),
    Venue("chiplay", "ACM SIGCHI Annual Symposium on Computer-Human Interaction in Play", "CHI PLAY", 1240, month=11),
    Venue("mobilehci", "International Conference on Human-Computer Interaction with Mobile Devices and Services", "MobileHCI", 937, month=9.5),
    Venue("tochi", "ACM Trans. Comput. Hum. Interact.", "TOCHI", 760, month=12),
]

VENUES_BY_KEY = {v.key: v for v in VENUES}

# --- 拡張 venue(引用結合フィルタで部分収録) ---
# コアの13会場と違い全論文は入れない: コアと引用リンクが1本以上ある論文だけを
# 拡張ビルド(build_graph --extended → data/viz-ext)に収録する。
# 名前と件数は 2026-07-30 に bulk search で実測。
# SIGGRAPH は 2003 年以降 TOG 掲載になるため、会議録と TOG の両方が要る。
EXTRA_VENUES: list[Venue] = [
    Venue("hri", "Human-Robot Interaction", "HRI", 4500, month=3),
    Venue("ieeevr", "IEEE Virtual Reality Conference", "IEEE VR", 2623, month=3.5),
    Venue("ismar", "International Symposium on Mixed and Augmented Reality", "ISMAR", 1213, month=10.1),
    Venue("siggraph", "International Conference on Computer Graphics and Interactive Techniques", "SIGGRAPH", 9307, month=8),
    Venue("tog", "ACM Transactions on Graphics", "TOG", 5020, month=8.2),
    Venue("ijhcs", "Int. J. Hum. Comput. Stud.", "IJHCS", 2803, month=6),
    Venue("toh", "IEEE Transactions on Haptics", "ToH", 1162, month=6.5),
]

EXTRA_KEYS = {v.key for v in EXTRA_VENUES}
VENUES_BY_KEY.update({v.key: v for v in EXTRA_VENUES})
CORE_KEYS = {v.key for v in VENUES}

# 注記:
# - CSCW は 2017 以降 PACM HCI に移行しているため、`cscw` と `pacmhci` の両方が必要。
#   PACM HCI には EICS / ISS / CHI PLAY も含まれるので、CSCW だけを厳密に取り出したい場合は
#   別途 issue 単位の判別が要る。今は「HCI コーパス」としてまとめて入れる。
# - UbiComp / IMWUT も同様に 2017 前後で分割されている。
