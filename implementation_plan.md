# 新LivePocket対応と検索キーワード強化の完成 (Phase 10)

本フェーズでは、システム刷新が行われた新 LivePocket (`livepocket.jp`) にクローラーを完全対応させるとともに、未コミット状態であった LivePocket 検索キーワード拡張・ノイズフィルター・生誕祭フィルターを統合して正式に本番運用できる体制を整えます。

## User Review Required

> [!IMPORTANT]
> **新 LivePocket への完全移行**
> 旧 LivePocket (`t.livepocket.jp`) は現在「過去履歴の閲覧専用（2026年9月閉鎖）」となっており、新着イベントは一切登録されません。そのため、本フェーズにて接続先を新サイトに完全移行（上書き）します。

> [!TIP]
> **誤検出フィルターの多層化**
> メンバー名検索（生誕祭の検知など）を増やすことで発生する無関係なアニソンライブやソロイベント等のノイズを、「タイトルに生誕・Birthday等の文字があるか」「本文にグループ表記ゆれワードがあるか」を判定する取得後フィルターによって強力に排除します。

---

## Proposed Changes

### 1. 新LivePocketサイト対応

#### [MODIFY] [livepocket.py](file:///C:/Users/takum/./.gemini/antigravity/scratch/idol-event-collector/scraper/livepocket.py)
- **検索エンドポイントの更新**: 巡回ドメインを `livepocket.jp` に、検索パラメータを `word` に変更。
- **絶対URL変換**: 個別イベントの `/e/XXXX` 相対パスから、新ドメインの `https://livepocket.jp/e/XXXX` への正規化を追加。
- **販売ステータスのクリーンアップ**: 取得したタイトルから「販売前」「販売中」「終了」などのステータス接頭辞を正規表現で自動削除する処理を追加。

### 2. 検索キーワード拡張とフィルター追加

#### [MODIFY] [config.py](file:///C:/Users/takum/./.gemini/antigravity/scratch/idol-event-collector/config.py)
- `livepocket_search_queries` リストを新設し、`東京CuteCute` および `Red radiance` の表記ゆれキーワードを追加（「レドラ」等の短い略称も含む）。

#### [MODIFY] [main.py](file:///C:/Users/takum/./.gemini/antigravity/scratch/idol-event-collector/main.py)
- **グループ/メンバー検索の分離**: 検索クエリを「グループ名の表記ゆれ」と「各メンバーの個人名」に分離して巡回。
- **生誕祭フィルター**: メンバー名での検索ヒットについて、タイトルに「生誕/生誕祭/Birthday」が含まれるか、あるいは本文に対象グループ名が含まれる場合のみ採用するフィルターを実装。
- **レドラの誤検知防止**: 部分一致ノイズを防ぐため、前後が日本語/英数字ではない場合のみ「レドラ」として採用する正規表現チェックを追加。

---

## Verification Plan

### Automated Tests
1. **フィルター動作の検証**:
   - `test_livepocket_filter.py` を実行し、無関係イベントの除外、生誕祭イベントの採択、およびキーワード拡張の妥当性をチェック。
   - `test_livepocket_resurrection.py` を実行し、各種モックテストが正常に通過することを確認。
   - コマンド: `py C:\Users\takum\.gemini\antigravity\brain\379fd0ad-b37b-4fa3-b2c6-8731c49be4cc\scratch\test_livepocket_filter.py`

### Manual Verification
- ローカル環境で `main.py` および単体スクレイピングを実行し、新 LivePocket (`livepocket.jp`) から実際のイベントが抽出され、タイトルから販売ステータスが綺麗に削除されていること、および過去日付のイベントが正しくスキップされることを確認。
