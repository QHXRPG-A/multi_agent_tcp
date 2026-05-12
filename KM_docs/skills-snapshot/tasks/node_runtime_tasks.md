## 2026-05-12 Agent ring circulation limits

Completed:

- Concrete AgentNode rings are detected from direct `exec` AgentNode edges.
- The smallest valid ring is two mutual Agents: `A -> B`, `B -> A`.
- Runtime owns independent counters for every ring, exposed per participating Agent as `{ring1: x, ring2: y}`.
- Each ring currently defaults to `max_circulations = 1`; later user configuration should write through `agent_ring_max_circulations`.
- A full circulation is counted on the ring closing edge, for example `D -> A` in `A -> B -> C -> D -> A` and `B -> A` in `A -> B -> A`.
- Nested rings, overlapping rings, and shared-edge rings keep separate counters.
- Once every ring that permits an edge is exhausted, active downstream connections remove that target and the framework rejects new forwarding batches for that edge.
- The implementation stays on ordinary outgoing batches / `agent.dispatch`; the old `RingSession*` scheduler remains archived.

Follow-up:

1. Surface `agent_rings` and per-Agent circulation counts cleanly in GuLiCode status views.
2. Add user-facing configuration/editing for per-ring maximum circulation counts.
3. Improve status explanation text for ring exhaustion and skipped downstream targets.
4. Keep regression coverage for two-node rings, shared-edge rings, nested/overlapping rings, and no-op dispatch.
# 鑺傜偣杩愯鏃朵笌鍥剧紪璇戞柟鍚戜换鍔?

> 褰撳墠瀹氫綅锛氭湰鏂囦欢鍙褰?GraphRuntime / graph scheduling / AgentNode runtime 鐨勪换鍔°€傛棫 Ryven `Start -> AgentNode -> End` 鏈€灏忛棴鐜槸鍘嗗彶闃舵锛屼笉鏄綋鍓?GuLiCode 浜у搧涓荤嚎銆傚綋鍓嶄紭鍏堢骇浠?`current_goals.md` 鍜?`multi_agent_communication_tasks.md` 涓哄噯銆?

## 鐩爣

鎶?GraphRuntime 杩愯鏃躲€佽妭鐐归槦鍒椼€佹秷鎭壒娆°€乫an-out/fan-in銆亀orkspace/events 鍜屾渶缁堢姸鎬佽仛鍚堟墦纾ㄦ垚 GuLiCode desktop 鍙緷璧栫殑鎵ц搴曞骇銆?

## 杩戞湡浠诲姟

### 褰撳墠鏈€楂樹紭鍏堢骇锛氬祵濂楃幆 / 鍒嗘敮鐜€掑綊澶勭悊

褰撳墠 `ring session` 鍙鐩栦竴涓畝鍗曞崟鍚戠幆鐨勫崟杞墽琛屻€備笅涓€姝ユ渶楂樹紭鍏堢骇鏄妸澶嶆潅鐜粨鏋勭撼鍏ヨ繍琛屾椂璇箟锛?
1. 鑷姩璇嗗埆宓屽鐜€佸叡浜妭鐐圭幆銆佸垎鏀幆鍜岄噸鍙?SCC锛屽尯鍒嗗彲鎶樺彔瀛愮幆涓庨渶瑕佹嫆缁濈殑姝т箟缁撴瀯銆?2. 灏嗗唴灞傜幆鎶樺彔涓哄灞傝瑙掍腑鐨勭幆绫?`Agent`锛岃澶栧眰鍙湅鍒版櫘閫氳妭鐐癸紝涓嶇洿鎺ヨ皟搴﹀唴灞傚洖璺€?3. 瀹氫箟鐖跺瓙 `ring session` 鐢熷懡鍛ㄦ湡锛氱埗浼氳瘽瑙﹀彂瀛愪細璇濄€佸瓙瀹℃牳瀹?final output 鍥炲～鐖朵細璇濄€佺埗浼氳瘽缁х画鍗曡疆鎺ㄨ繘銆?4. 瀹氫箟璺ㄥ眰鍏ュ彛娑堟伅鍚堝苟銆佸姩鎬佸彲杈捐妭鐐圭户鎵裤€佸鏍稿畼骞傜瓑杈撳嚭銆佽秴鏃躲€佸け璐ャ€佸彇娑堝拰杩熷埌娑堟伅澶勭悊銆?5. 淇濇寔褰撳墠绠€鍗曞崟鐜疄鐜颁负 base case锛屼笉鎶婂杞洖娴佹垨鏃犲簭鍙嶆祦娣疯繘鏈疆璁捐銆?
### 澶?Agent 閫氫俊璁捐

褰撳墠鑺傜偣杩愯鏃舵柟鍚戠殑棣栬浠诲姟鎷嗚В瑙?[`multi_agent_communication_tasks.md`](multi_agent_communication_tasks.md)銆傚巻鍙茶璁＄鍙弬鑰?skill 鏍圭洰褰曠殑 `澶歛gents閫氫俊璁捐.md`锛屼笉瑕佸啀浣跨敤鏃?`F:\src\ryven_demo` 浣滀负榛樿璺緞銆?
宸插畬鎴愮涓€闃舵锛?

- 涓€瀵瑰 outgoing batch 鏆傚瓨涓庡畬鏁存壒娆″叆闃燂紱
- `remaining_targets` 琛ラ綈鎻愰啋锛?
- 浠?`GraphDefinition` 鑷姩鐢熸垚 `agent_connections`锛?
- `agent_organization_view()` 鍒濈増缁勭粐瑙嗗浘锛?
- 鍚姩鐐圭敱 GuLiCode / 椤跺眰 Agent 鏄惧紡鎸囧畾锛屾鏋跺彧鏍￠獙锛?
- GuLiCode 椤跺眰 Agent rule / skill / start plan validation 楠ㄦ灦銆?

涓嬩竴姝ヤ紭鍏堬細

1. 缁勭粐鏋舵瀯鎺ュ彛锛?
2. 寮€濮嬫帴鍙ｏ紱
3. 鏅€?Agent 娑堟伅鍒嗗彂 RPC/tool锛?
4. 澶氬涓€ fan-in / join锛?5. 鐘舵€佹煡璇笌缁撴潫/鏈€缁堣仛鍚堟帴鍙ｃ€?
### 2026-05-11 鐜姸缁撴瀯 / ring session runtime

宸插畬鎴愬苟绾冲叆褰撳墠鐭ヨ瘑锛?
- 鐜被 `agent` 瀵瑰瑙嗕负鏅€?`agent`锛屽鍐呮寜鍗曞悜鍗曡疆娆℃墽琛屼細璇濇祦杞紱
- `RingSessionEntry` / `RingSessionPlan` / `RingSessionState` 宸茶惤鍦板埌杩愯鏃讹紱
- `GraphDefinition.plan_ring_session()` 涓?`plan_ring_session_from_entries()` 宸插彲鏍规嵁鐜『搴忓拰鍏ュ彛娑堟伅鐢熸垚浼氳瘽璁″垝锛?- `GraphRuntime.register_ring_session()`銆乣ring_session_reachable_targets()`銆乣ring_session_dispatch_targets()`銆乣ring_session_state()` 宸叉敮鎸佸姩鎬佸彲杈捐妭鐐广€侀槦鍒楅棬鎺у拰瀹℃牳瀹?final output锛?- 鎺у埗闈㈠凡鏀寔 `ring.register`锛屽苟涓庢櫘閫氭秷鎭壒娆?/ 鍒嗗彂璺緞鍏辩敤妗嗘灦鎺ュ彛锛?- 宸查獙璇?`python -m pytest test_agent_runtime.py test_graph_control.py test_workspace_api.py test_workspace_manager.py -q` 涓?`120 passed`銆?
鐭湡鏀跺彛锛?
1. 浼樺厛澶勭悊涓婃柟鈥滃祵濂楃幆 / 鍒嗘敮鐜€掑綊澶勭悊鈥濅换鍔°€?2. 鎶?ring-session 鐨勯槦鍒椾笂闄愩€佽秴鏃躲€佸鏍稿畼骞傜瓑杈撳嚭銆佽繜鍒版秷鎭樆鏂紝缁х画淇濈暀鍦?runtime 鐘舵€佷笌浜嬩欢瑙ｉ噴閲屻€?3. 缁х画鎶?`knowledge_base/ring_structure_solution.md` 浣滀负褰撳墠 ring 鏂规鐨勪富鏂囨。銆?
### 鍘嗗彶鏈€灏忛棴鐜矾寰勶紙宸查檷绾э級

浠ヤ笅璺緞鏇剧敤浜?Ryven / runtime 铻嶅悎鏃╂湡楠岃瘉锛岀幇鍦ㄥ彧浣滀负鍘嗗彶鑳屾櫙锛?

1. `Start -> blocking AgentNode -> End`
2. 鐢?Ryven Flow 缂栬瘧鎴?`GraphDefinition`
3. 鐢变竴涓渶钖勭殑鍥炬墽琛屽櫒鎸?`exec` 杈硅窇閫?
4. 鑺傜偣杩愯鐘舵€佸彲瑙侊紝鏈€缁堢粨鏋滃彲瑙?
5. 杩愯缁撴灉鍏堝洖鍐欏埌 UI / 鏃ュ織锛屽悗缁啀杩涘叆浜嬩欢鎬荤嚎

杩欐潯璺緞褰撴椂鐨勫師鍒欙細
- 涓嶅厛鍋氬畬鏁磋矾鐢辩郴缁?
- 涓嶅厛鍋?nonblocking job 鎸佷箙鍖?
- 涓嶅厛鍋氬鏉?Inspector / 绫诲瀷绯荤粺
- 涓嶅厛鍋氬垎甯冨紡 workspace 鍗忎綔
- 鍏堢‘淇濆崟鑺傜偣鍥鹃棴鐜ǔ瀹?

杩欐壒鏃ч樁娈典换鍔′腑锛屼粛鐒舵湁鏁堢殑杩愯鏃堕儴鍒嗗凡缁忚縼绉诲埌褰撳墠 GraphRuntime / GuLiCode 涓荤嚎锛汻yven/editor 涓撳睘閮ㄥ垎寤跺悗銆備繚鐣欎互涓嬫潯鐩粎鐢ㄤ簬鐞嗚В鍘嗗彶鏉ユ簮锛?

1. AgentNode prompt contract锛屼娇涓嬫父 agent 鍙煡鏅擄細
   - 浼犲叆涓婁笅鏂?
   - 鐢ㄦ埛璁剧疆鐨?agent prompt / model / skills
   - 妗嗘灦鍏佽鏆撮湶鐨勬帴鍙ｆ枃妗?
   - 鍙/鍙啓璺緞
   - 杈撳嚭鏍煎紡
2. `AgentSkillSelection` 鍒板浘鎵ц鏈熺殑鎺堟潈 skill 娉ㄥ叆锛?
   - `none` / `all` / `selected` / `upstream` 妯″瀷宸茶惤鍦?
   - registry / registry-ui 宸插悓姝?
   - 褰撳墠浠嶉渶鎶?`upstream` 涓庡浘涓婃父瓒呯骇 agent 鐨勯厤缃祦銆佹巿鏉?skill materialize 涓茶捣鏉?
3. `AgentSkillView` 涓?CodexAdapter 鐨勫己闅旂锛?
   - prompt/context 娉ㄥ叆宸插彲鐢?
   - 涓存椂 `CODEX_HOME` 宸茬粦瀹氬埌 agent 绉佹湁鐩綍
   - Codex 钃濆浘鍚姩宸蹭娇鐢?`workspace-write` sandbox + private checkout `cwd`锛屽苟鎷掔粷 `danger-full-access` 涓庢妸鐪熷疄椤圭洰鐩綍鍔犲叆 `--add-dir`
4. 瓒呯骇 agent 涓嬫父 agent 閰嶇疆鑳藉姏锛?
   - model
   - skills
   - prompt contract
   - write/artifact scope
5. 澶勭悊鑺傜偣銆両/O 鑺傜偣鍜屾潯浠?`switch` 璺敱銆?
6. 鍙闃?鍙寔涔呭寲浜嬩欢娴侊紝浠ュ強 `WorkspaceChanged`銆乣ReviewRequested` 鐨勫疄闄呰Е鍙戠偣銆?
7. 闈為樆濉?job 鐨勫彇娑堛€佹仮澶嶃€佽秴鏃躲€佸け璐ラ噸璇曞拰鎸佷箙 runner銆?
8. 鍏变韩宸ヤ綔鍖?lock / lease銆丏ulwich commit/ref merge銆佸綊妗ｅ垹闄?API銆佸綊妗ｇ储寮曞拰绌洪棿娓呯悊绛栫暐銆?
9. Ryven + GraphRuntime 铻嶅悎椤哄簭锛?
   - 绗竴姝ワ細Ryven Flow -> `GraphDefinition` 缂栬瘧 + `validate_runnable`锛堝凡瀹屾垚锛?
   - 绗簩姝ワ細鍙窇 blocking `AgentNode` 鐨勬渶灏忛摼璺?
   - 绗笁姝ワ細鏄剧ず姣忎釜鑺傜偣鐨勮繍琛岀姸鎬佸拰鏈€缁堢粨鏋?
   - 绗洓姝ワ細鎺?nonblocking job / manifest / workspace event
   - 绗簲姝ワ細鍋氭洿寮虹殑绫诲瀷绯荤粺銆両nspector銆佷笂涓嬫枃鎺ㄨ崘

### Ryven 鏈€灏忛棴鐜柟妗堝蹇橈紙寤跺悗锛?

濡傛灉鏈潵閲嶆柊鍚姩 Ryven/editor 鏂瑰悜锛屽彲鍙傝€冧互涓嬬瓥鐣ワ細

1. 鍏堟妸鍥炬墽琛屽櫒闄愬埗涓哄崟涓€鎵ц璺緞锛屽彧鏀寔 `Start -> AgentNode -> End`
2. 鍙厑璁镐竴涓?blocking AgentNode 鍏堣窇閫氬畬鏁村洖璺?
3. 鎶?`AgentNode` 鐨勮緭鍏ヨ緭鍑哄厛鍥哄寲涓烘渶灏戠鍙ｈ涔夛細
   - `in` 绔彛鎺?exec
   - `prompt` 绔彛鎺?data
   - `out` 绔彛缁х画 exec
   - `result` 绔彛鍥炰紶 data
4. 鍏堝湪 UI 涓睍绀烘墽琛屼腑 / 瀹屾垚 / 澶辫触涓夋€?
5. 缁撴灉鍏堟樉绀哄湪鑺傜偣闈㈡澘鎴栨棩蹇楃獥锛屼笉鎬ョ潃鍋氬鏉備簨浠堕潰鏉?
6. 閫氳繃涓€涓樉寮忊€淩un Blueprint鈥濆姩浣滆Е鍙戣繍琛岋紝鑰屼笉鏄竴寮€濮嬪氨鍋氳嚜鍔ㄨ皟搴?

### 宸ヤ綔鍖鸿亴璐ｅ榻?

鐭湡闇€瑕佹妸宸ヤ綔鍖烘ā鍨嬩粠鈥渏ob worktree 鑷姩鍚堝苟鈥濊皟鏁翠负鏇存竻鏅扮殑涓夊眰锛?

1. `base/`锛氭湰娆¤摑鍥捐繍琛屽紑濮嬫椂鐨勯」鐩熀绾匡紝鐢ㄤ簬 diff / merge / conflict 鍒ゆ柇銆?
2. `agents/<agent_id>/private/`锛歛gent 绉佹湁 scratch 绌洪棿锛屽瓨鏀句复鏃舵枃浠躲€佺紦瀛樸€佹巿鏉?skills view銆丆LI 浼氳瘽鏁版嵁绛夛紱钃濆浘缁撴潫鍚庨攢姣侊紝涓嶅綊妗ｃ€佷笉鑷姩鍚堝苟銆?
3. `shared/`锛氭湰娆¤摑鍥捐繍琛岀殑涓存椂鍏变韩鎴愭灉绌洪棿锛屽瓨鏀句唬鐮佷慨鏀广€佺敓鎴愬浘鐗囥€佺敓鎴愭枃鏈€佹姤鍛娿€乵anifest 绛夊叾瀹?agent 闇€瑕佽鍙栨垨鏈€缁堥渶瑕佸綊妗ｇ殑浜х墿銆?

蹇呴』瀵归綈鐨勮鍒欙細

- agent 绉佹湁绌洪棿鍙互鏄嫭绔嬬洰褰曪紝涔熷彲浠ュ悗缁崌绾т负 Git/Dulwich worktree锛涗絾璇箟涓婂畠涓嶆槸鎴愭灉鐩綍銆?
- 绉佹湁绌洪棿鍐呭涓嶈嚜鍔ㄨ繘鍏?`shared/`锛沘gent 闇€瑕佹樉寮忓彂甯冩垚鏋滃埌鍏变韩绌洪棿銆?
- 鍏变韩绌洪棿鍐欏叆蹇呴』鏈夌珵鎬佸鐞嗭紝鑷冲皯鍏堣惤鍦版枃浠剁骇 lock / lease + manifest 璁板綍锛涘悗缁啀鍗囩骇鍒?Dulwich commit/ref merge銆?
- 澶?agent 鍚岃矾寰勫啓鍏ユ椂涓嶈兘闈欓粯瑕嗙洊锛屽繀椤昏繑鍥炲啿绐佺姸鎬佸苟淇濈暀瓒冲淇℃伅缁欎汉宸ユ垨涓婂眰 agent 瑙ｅ喅銆?

## 褰撳墠浠ｇ爜瀵圭収鐘舵€侊紙2026-05-04锛?

宸插畬鎴愶細

1. 宸叉柊澧?`graph_runtime.py`锛屽寘鍚?`AgentNode`銆乣AgentInstance`銆乣GraphRuntime`銆乣BrokerAgentRuntime`銆?
2. `AgentNode` 宸插叿澶囦笌 `WorkerConfig` / registry 鎵╁睍瀵归綈鐨勫熀纭€瀛楁锛歚node_id`銆乣agent_id`銆乣cli_kind`銆乣model`銆乣cwd`銆乣skills`銆乣timeout_sec`銆乣prompt_via_file`銆乣command`銆乣adapter_options`銆乣extra_env`銆乣external`銆?
3. `GraphRuntime.ensure_agent()` 宸插疄鐜板悓涓€娆″浘杩愯鍐呯殑 `node_id -> AgentInstance` 缁戝畾涓庡鐢紱棣栨缁忚繃鑺傜偣鍙皟鐢?`cluster.ensure_worker()` 鎳掑惎鍔?worker銆?
4. `GraphRuntime.send_agent_message()` 宸叉妸 Agent 鑺傜偣娑堟伅鍙戦€佹槧灏勫埌 `cluster.run_single()`锛屽苟鏄庣‘鎶?cluster 鏂规硶瑙嗕綔娑堟伅璋冨害鍘熻锛岃€屼笉鏄瘡娆¤妭鐐圭粡杩囬兘 spawn/teardown銆?
5. `BrokerAgentRuntime` 宸叉彁渚涜繛鎺ュ凡鏈?broker 骞跺悜 worker 鍙戦€佸崟鏉℃秷鎭殑杞婚噺杩愯鏃躲€?
6. `AgentNode.execution_mode` 宸叉敮鎸?`blocking` / `nonblocking` 瀛楁鏍￠獙锛沗GraphRuntime.send_agent_message()` 浼氭妸 `nonblocking` 鑺傜偣杞负 job 鎻愪氦鍝嶅簲銆?
7. 宸叉柊澧?`GraphJob`銆乣GraphEvent`銆乣WorkspaceManifest`锛屽舰鎴愰潪闃诲 job銆佷簨浠舵ā鍨嬩笌鍏变韩宸ヤ綔鍖?manifest 鐨勬渶灏忓彲搴忓垪鍖栧熀绾裤€?
8. 宸叉柊澧?`MultiModalEnvelope` / `normalize_envelope`锛屼綔涓鸿妭鐐圭鍙ｇ粺涓€鏁版嵁瀹瑰櫒銆?
9. 宸叉柊澧?`RouteNode`銆乣GraphEdge`銆乣GraphDefinition`銆乣GraphExecutor`锛屾敮鎸?DAG 鐜娴嬪拰 `sequence` / `parallel` / `parallel_reduce` 璺敱鍒?cluster 鍘熻鐨勬渶灏忓疄鐜般€?
10. 宸叉柊澧?`dulwich_vendor.py` 涓?`workspace_manager.py`锛屾帴鍏?vendored Dulwich锛屽苟瀹炵幇鐢ㄦ埛鍙寚瀹氱殑椤圭洰绾ч暱鏈熷叡浜伐浣滃尯銆佽摑鍥捐繍琛岀骇涓存椂鍏变韩宸ヤ綔鍖恒€佸畬鏁寸洰褰曞綊妗ｃ€乯ob 闅旂 worktree銆乨iff銆乻cope 鏍￠獙銆佹枃鏈笁鏂?merge 鍜屽啿绐佹娴嬨€?
11. 闀挎湡鍏变韩宸ヤ綔鍖烘敮鎸侀粯璁?`<project>/.multi_agent_workspace/`锛屼篃鏀寔鐢ㄦ埛鏄惧紡浼犲叆 `workspace_root`锛涘綋瀹冧綅浜庡伐绋嬬洰褰曞唴鏃讹紝杩愯蹇収浼氭帓闄よ鐩綍銆俛gent 璁块棶涓婁笅鏂囦細鎶婇暱鏈熷叡浜伐浣滃尯鏆撮湶涓?`readonly_shared_workspaces`锛屽苟鎷掔粷鎶婂畠绾冲叆 `write_scope` / `artifact_scope`銆?
12. 宸叉柊澧?`SkillSpace`銆乣AgentSkillView`銆乣SuperAgentProfile`锛氭鏋剁鏈夌淮鎶?hash -> skill 鐨勬槧灏勶紝鎸?hash 鍒楄〃灏嗘巿鏉?skills 澶嶅埗鍒板綋鍓?agent 鐙珛鐩綍锛屽苟涓鸿秴绾?agent 鎻愪緵涓嬫父 skill 鍒嗛厤鏍￠獙銆?
13. `test_agent_runtime.py` 宸茶鐩?AgentNode 瀛楁瑙ｆ瀽銆乄orkerConfig 杞崲銆丟raphRuntime 鎳掑惎鍔ㄤ笌澶嶇敤銆侀潪闃诲 job 浜嬩欢鍜?manifest銆丮ultiModalEnvelope銆丏AG 鐜娴嬨€佽矾鐢辫妭鐐硅皟搴︺€?
14. `test_workspace_manager.py` 宸茶鐩?Dulwich backend銆佸畬鏁寸洰褰曞綊妗ｃ€佽嚜瀹氫箟闀挎湡鍏变韩鐩綍銆佸彧璇昏闂瓥鐣ャ€乯ob diff銆乻cope violation銆佹棤鍐茬獊鍚堝苟銆佸悓鏂囦欢鍐茬獊鍜?failed run 褰掓。銆?
15. `test_skill_space.py` 宸茶鐩?hash skill 鏄犲皠銆乤gent 鐙珛鐩綍 materialize銆佹湭鐭?hash 鎷掔粷銆佽秴绾?agent 鍒嗛厤鏉冮檺鍜?workspace manager 鐨?agent 鐩綍闆嗘垚銆?
16. `AgentSkillView` 宸叉柊澧?`codex_execution_context()` 涓?`codex_adapter_options()`锛屽彲鍚?CodexAdapter 鏆撮湶 agent 鐙珛鐩綍銆乧ache銆佹巿鏉?skills 鐩綍銆乻kill hash 鍒楄〃涓庢巿鏉?skill catalog銆?
17. `AgentNode.node_id` 宸叉敼涓烘鏋惰嚜鍔ㄥ垎閰嶏紱鐢ㄦ埛閰嶇疆渚т笉鍐嶉渶瑕佸～鍥惧唴閮ㄨ妭鐐?ID銆?
18. `AgentSkillSelection` 宸茶惤鍦板苟鍚屾鍒?registry / registry-ui锛屾敮鎸?`none`銆乣all`銆乣selected`銆乣upstream`锛涙棫 `skills` 鍒楄〃鍏煎涓?`selected`銆俽egistry 闈欐€佹敞鍏ヤ腑 `upstream` 涓嶈В鏋?skill锛岀暀缁欏浘杩愯鏃惰秴绾?agent 鎺堟潈銆?
19. `test_registry_skill_selection.py` 宸茶鐩?registry 瀵?skill selection 鐨勮В鏋愩€乧atalog 娉ㄥ叆鍜?`show-registry` 杈撳嚭銆?
20. `AgentNode.to_dict()` 宸茶ˉ榻愶紝渚夸簬 Ryven wrapper銆侀」鐩繚瀛樺拰 runtime 缂栬瘧澶嶇敤鍚屼竴鍚庣 schema銆?
21. `GraphDefinition` 宸叉柊澧?`BlueprintTerminalNode`銆乣terminal_nodes` 鍜?`validate_runnable()`锛屽彲鏍￠獙 Start/End 鍞竴鎬с€丏AG 涓?start -> end 鏈夊悜璺緞銆?
22. `GraphEdge` 宸叉柊澧?`edge_type`锛岀敤浜庤褰曠鍙ｈ繛鎺ヨ涔夛紱`validate_runnable()` 鍙娇鐢?`exec` 杈瑰垽鏂?Start -> End 鎺у埗娴佽矾寰勶紝`data` 杈逛笉浼氳鍒や负鍙繍琛岃矾寰勩€?
23. `compile_ryven_flow()` 宸插彲鎶?live Ryven flow 缂栬瘧涓?`GraphDefinition`锛歚BlueprintStart` / `BlueprintEnd` 缂栬瘧涓?`BlueprintTerminalNode`锛孯yven `AgentNode` wrapper 缂栬瘧涓哄悗绔?`AgentNode`锛孯yven 杩炴帴缂栬瘧涓哄甫绔彛鍚嶅拰 `edge_type` 鐨?`GraphEdge`銆?

閮ㄥ垎瀹屾垚锛?

1. 鑺傜偣鍒嗙被鐩墠鍙惤鍦颁簡 Agent 鑺傜偣锛涘鐞嗚妭鐐广€佽矾鐢辫妭鐐广€両/O 鑺傜偣浠嶅仠鐣欏湪璁捐浠诲姟銆?
2. Agent 鑺傜偣鐢熷懡鍛ㄦ湡宸叉湁鈥滈娆＄粦瀹?鍚庣画澶嶇敤/杩愯鏃?close 娓呯悊缁戝畾鈥濈殑鍩虹瀹炵幇锛涚敱 cluster 鎷ユ湁鐨?worker 杩涚▼ teardown 浠嶅鎵樼粰 cluster锛屽皻鏈舰鎴愬畬鏁村浘杩愯澶辫触/鍙栨秷鏀跺熬鍗忚銆?
3. 鍥剧紪璇戠洰鍓嶅凡鏈夎矾鐢辫妭鐐瑰埌 `run_chain` / `run_parallel` / `run_parallel_reduce` 鐨勬渶灏忔槧灏勶紝骞舵柊澧?runnable blueprint 璧锋绾︽潫锛汻yven flow -> `GraphDefinition` 缂栬瘧宸茶惤鍦扮涓€鐗堬紝浣嗚繕娌℃湁鍥剧骇 blocking 鎵ц鍏ュ彛鍜屼簨浠跺洖娴?UI銆?
4. 鍏变韩宸ヤ綔鍖哄凡鏈夐殧绂荤洰褰曘€乨iff銆乵erge銆佸啿绐佹娴嬨€佸畬鏁寸洰褰曞綊妗ｅ拰 runtime 鍙绛栫暐锛汣odex strict launch 渚濊禆 `workspace-write` sandbox 鍜屽惎鍔ㄥ弬鏁版牎楠岋紱lock / lease銆佹寔涔?runner銆丟it 瀵硅薄绾?commit/ref merge 浠嶆湭鍋氥€?
5. 宸ヤ綔鍖烘ā鍨嬪凡寮€濮嬪悜 `base/` + `shared/` + `agents/<agent_id>/private/` 鎷嗗垎锛氱鏈夌洰褰曞彧浣滀负 scratch锛屽綊妗ｅ墠涓㈠純锛涘叡浜洰褰曚繚鐣欐垚鏋滐紝骞跺凡鏈夋渶灏忔枃浠剁骇 lease API銆傚畬鏁磋繍琛屾湡绔炴€佸鐞嗐€乵anifest 鍗忚鍜?Dulwich commit/ref merge 浠嶆湭瀹屾垚銆?
6. 浜嬩欢妯″瀷鐩墠鏄唴瀛樺垪琛ㄥ拰 manifest 鏇存柊锛涜繕涓嶆槸璺ㄨ繘绋嬩簨浠舵€荤嚎銆?
7. SkillSpace 鐩墠鎻愪緵鐩綍绾ч殧绂讳笌 prompt/context 鏆撮湶锛涘凡鍙敓鎴?CodexAdapter options锛屼絾灏氭湭鎶婁复鏃?`CODEX_HOME` 鑷姩缁戝畾鍒?CLI 杩愯鏃跺仛寮洪殧绂汇€?
8. `upstream` skill selection 鐨勮繍琛屾椂鎺堟潈妯″瀷宸叉湁鏍￠獙鍩虹锛屼絾杩樻病鏈夊畬鏁存帴鍏ュ浘涓婃父瓒呯骇 agent 鐨?UI/缂栨帓閰嶇疆娴併€?

鏈畬鎴?/ 涓嬩竴姝ワ細

1. 瀹屾垚 graph scheduling beyond minimal single exec path锛歱arallel branches銆乫an-out/fan-in銆乧ondition/switch routing銆乶onblocking job joins銆乨eterministic final state aggregation銆?
2. 鎶?ordinary-Agent dispatch 缁戝畾鍒板綋鍓?task envelope銆乷utgoing batch 鍜?`required_outgoing_targets`銆?
3. 鎶?workspace/VCS API銆乤rtifact/report publish API 缁熶竴缁戝畾鍒板綋鍓嶄换鍔′俊灏佸拰 Agent scope銆?
4. Surface runtime events to GuLiCode desktop锛歲ueued銆乨ispatching銆乺unning銆亀aiting_for_reply銆乯oin waiting銆乧ompleted銆乫ailed銆乧ancelled銆亀orkspace changed銆?
5. 灏?`AgentSkillView` / Codex adapter options 鑷姩骞跺叆 AgentNode / WorkerConfig 鍒涘缓璺緞銆?
6. 灏?`upstream` skill selection 涓庡浘涓婃父瓒呯骇 agent 閰嶇疆娴佹墦閫氾紝骞跺湪闇€瑕佹椂鐢辫繍琛屾椂 materialize 鎺堟潈 skills銆?
7. 瀹炵幇瓒呯骇 agent 闄?skill 鍒嗛厤澶栫殑涓嬫父 agent 閰嶇疆鑳藉姏銆?
8. Ryven/editor 鐩稿叧鐨?Run Blueprint銆丼tart/End 鏈€灏忛摼璺€両nspector 鍜岃妭鐐硅瑙夋敼閫犲欢鍚庡埌鏄庣‘闇€瑕?visual editor 鏃躲€?

## 2026-05-11 `GraphDefinition.agent_cycle_groups()`锛堝凡钀藉湴锛?

- 鏂板 `GraphDefinition.agent_cycle_groups()`锛氬湪浠?**`exec` 杈?* 鐨勫瓙鍥句笂鍋?SCC锛涜嫢 SCC 涓虹幆锛堝惈澶氱偣 SCC 鎴栧甫鑷幆鐨勫崟鐐癸級锛屽垯杈撳嚭璇?SCC 鍐呮墍鏈?**Agent** 鐨?`node_id`锛屾牸寮忎负浜岀淮鍒楄〃锛屼緥濡?`[["a", "b", "c"], ["d", "e", "f"]]`锛涙棤鐜浘杩斿洖 `[]`銆?
- 鐜嫢缁忚繃 **`RouteNode`锛堟垨鍏跺畠闈?Agent 鑺傜偣锛?* 浠嶅彲琚瘑鍒紝鍥犱负 SCC 鍦?*鍏ㄨ妭鐐?*涓婅绠楋紝杩斿洖鏃跺啀绛涙垚浠?agent id銆?
- 浠ｇ爜锛歚graph_runtime.py`锛涙祴璇曪細`test_agent_runtime.py`锛堝惈涓婅堪涓や緥锛夛紱璇ユ枃浠?pytest 鍦ㄥ悎鍏ユ椂涓?**64 passed**銆?
- 鍚庣画鍙€夛紙鏈仛锛夛細鍐嶅寘涓€灞傦紝鍚屾椂杈撳嚭銆屾瘡涓幆瀵瑰簲鐨勫師濮?SCC 鑺傜偣鍏ㄩ泦銆嶄究浜庤皟璇曞浘缁撴瀯銆?

## 渚濊禆鐭ヨ瘑

- [`../knowledge_base/multi_cli_workflow.md`](../knowledge_base/multi_cli_workflow.md)
- [`../knowledge_base/agent_node_ryven_integration.md`](../knowledge_base/agent_node_ryven_integration.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)
- [`../knowledge_base/cluster_api.md`](../knowledge_base/cluster_api.md)

## 2026-05-06 workspace alignment progress

- `workspace_manager.py` now splits each blueprint run into `base/`, `shared/`, and `agents/<agent_id>/private/`.
- `agents/<agent_id>/private/` is private scratch and CLI state. It is not an outcome worktree, is not auto-merged, and is discarded by `archive_run()` before archival.
- `shared/code/` is the per-run code outcome area, `shared/artifacts/` stores generated assets, and `shared/reports/` stores reports and structured results. These paths are preserved in the run archive.
- `shared/.locks/`, `acquire_shared_lease()`, `release_shared_lease()`, and `write_shared_text()` provide the first file-level lease and manifest path to prevent silent same-path overwrites.
- `ryven_blueprint.py` now points AgentNode `cwd` at private scratch and injects the Workspace API contract instead of exposing shared workspace paths as the primary interface.
- `codemaker_bridge.py` now consumes the same `prompt_preamble` and `execution_context` fields as `codex_bridge.py`, so both CodeMaker and Codex CLI-backed AgentNodes receive the workspace contract in their actual prompt.
- The blueprint controller writes `shared/reports/blueprint_result.json` before archive, recording run status, events, result, and the private workspace mapping.
- Compatibility note: legacy `prepare_job()` / `merge_job()` remains for old isolated-worktree tests and later Dulwich merge experiments, but the minimum blueprint run path no longer auto-merges private scratch as task output.

2026-05-06 follow-up:

- Added `docs/workspace_api.md` as the framework-maintained Workspace API contract for blueprint agents.
- Added `workspace_api.py` with `publish`, `publish-file`, `read`, and `list` commands. Agents publish to logical areas (`code`, `artifacts`, `reports`) instead of writing to physical shared workspace paths.
- Blueprint AgentNode startup now injects the Workspace API document and command contract, not the shared workspace paths. Agent `cwd` is private scratch; the API context is provided through `MULTI_AGENT_WORKSPACE_CONTEXT`.
- `publish` and `publish-file` go through `DulwichWorkspaceManager` shared write APIs and lease/manifest recording.
- Shared files now use a per-path read/write lock: concurrent reads are allowed, but any active writer blocks readers and writers, and active readers block writers.
- Workspace API also exposes per-path write versions: agents can `read --json`, edit privately, then `publish --expected-version N` to avoid stale overwrites during multi-agent edits.
- Remaining caveat: this is a controlled CLI API and prompt contract, not a full security boundary for every possible CLI backend. Codex strict launch currently relies on Codex `workspace-write` sandbox semantics; other backends need separate evaluation before being treated as strict.

Still pending:
- Move Workspace API from local context-file CLI to a broker-side or runtime-owned RPC/tool protocol.
- Add conflict records, conservative three-way merge, or Dulwich commit/ref merge for `shared/code/`.
- Wire `WorkspaceChanged` and `ReviewRequested` events to shared manifest updates.
- Define UI-visible policies for binary artifacts, deletes/renames, and scope violations.

## 2026-05-06 archived task status

Completed and archived into `archive/blueprint_integration_archive.md`:

- Blueprint run workspace split: `base/`, private scratch, and shared outcome areas.
- AgentNode startup now uses private scratch as `cwd`.
- Framework-maintained Workspace API document is injected into agents at startup.
- `workspace_api.py` provides controlled `publish`, `publish-file`, `read`, and `list` commands.
- Workspace API writes go through manager-owned lease and manifest recording.
- Shared files have per-path read/write locks: concurrent reads are allowed, writers are exclusive.
- Shared files have per-path versions for read-modify-write: `read --json` plus `publish --expected-version N`.
- Pytest coverage now includes Workspace API binary stale-version conflicts, API-level reader/writer blocking, active-reader publish blocking, path escape rejection, and the private `agents/<agent_id>/private/` SkillSpace integration expectation. Full project pytest is configured to skip vendored/generated dependency trees and currently passes with `59 passed`.

Current short-term follow-up:

- Promote Workspace API from local context-file CLI to broker/runtime-owned RPC or tool calls.
- Add conflict records and optional Dulwich commit/ref merge for `shared/code/`.
- Emit `WorkspaceChanged` events from Workspace API publish/read flows and surface them in the UI.
- Define UI-visible policies for binary artifacts, deletes/renames, and scope violations.

## 2026-05-07 VCS-style workspace task update

The file/snapshot VCS-style workspace MVP is now implemented and tested in the codebase.

Completed:

- `checkout/status/diff/submit/sync` exist at manager, RPC, and CLI levels.
- Agent private checkouts are now compatible with two code modes:
  - legacy `snapshot_copy`, copied from current `run.integration_dir`;
  - active `project_reference`, fetched on demand from the project directory.
- `workspace_api checkout --path <relative-file-or-dir>` supports focused task-level materialization; `--scope-path` remains available for broader scopes.
- In `project_reference`, empty scope no longer means full-project checkout/write access; it starts empty and rejects out-of-scope submit changes.
- Each checkout keeps its own base snapshot under `agents/<agent_id>/private/state/base`.
- Submit compares checkout base, current code target, and agent checkout to decide accept/conflict.
- In `project_reference`, accepted changes write back to the project directory; temporary shared workspace records changeset/conflict metadata rather than serving as code integration storage.
- Conflict responses are structured and preserved over RPC.
- The conflict repair loop is tested end to end.
- Text merge uses Dulwich `merge_blobs()` when available and falls back to conservative conflict behavior otherwise.
- `merge3` is recorded as the recommended dependency for Dulwich hunk-level text merging.

Next runtime tasks:

1. Continue reducing remaining legacy `integration_dir` / `shared_code` wording in status surfaces and docs by using the code-source/code-target abstraction.
2. Prefer `checkout --path -> edit -> status/diff -> submit` for source edits; keep `publish` for reports/artifacts, summaries, references, and non-source outputs.
3. Launch strict agents with project context read-only and private checkout writable.
4. Attach changeset ids, conflict ids, test results, and repair attempts to `TaskCompleted` / final blueprint reports.
5. Surface `CheckoutCreated`, `ChangesetSubmitted`, `ChangesetAccepted`, `ConflictDetected`, `CheckoutSynced`, and `WorkspaceChanged` in the UI/runtime event stream.
6. Define submit policies for binary files, deletes, renames, formatter-only changes, generated files, and large files.
7. After the file/snapshot RPC contract stabilizes, evaluate Dulwich commit/ref storage for baseline and integration refs.

## 2026-05-07 runtime tick and graph scheduling priority update

Completed:

- `GraphRuntime` now has a framework tick loop with a default 0.5-second frame interval.
- `AgentInstance` now tracks a fuller lifecycle state vocabulary and state history, covering startup, idle, queued, dispatching, running, waiting for reply, processing reply, failure, timeout, cancellation, restart, and stop phases.
- Runtime-managed per-agent queues now retain messages that arrive while a CLI-backed AgentNode cannot accept work.
- Each tick can dispatch queued messages FIFO, one message per idle agent per frame.
- Codex-backed AgentNode output was verified through the real `AgentNode -> GraphRuntime -> codex worker` path.
- Codex final reply display should use `reply.body.codex.final_text`; raw `stdout` remains JSONL debug/archive data, and `stderr` should be treated as diagnostic noise unless an error needs inspection.
- Windows Codex command resolution now avoids `.ps1` direct execution and prefers npm `.cmd` shims.

New top priority:

1. Complete graph scheduling beyond the minimal single exec path:
   - `parallel` branches;
   - fan-out/fan-in;
   - `condition` / `switch` routing;
   - nonblocking job joins;
   - deterministic final state aggregation.
2. Define scheduler frame semantics:
   - ready nodes;
   - blocked nodes;
   - running nodes/jobs;
   - completed branches;
   - failed/cancelled/timed-out branches;
   - join nodes waiting for upstream requirements;
   - terminal aggregation.
3. Define fan-out semantics:
   - how one upstream output becomes multiple downstream tasks;
   - how source metadata, task id, branch id, and parent output are carried;
   - how branch-level errors are reported without losing successful sibling outputs.
4. Define fan-in semantics:
   - wait-all, wait-any, quorum, and timeout policies;
   - how accepted changesets, conflicts, artifacts, reports, and test results are merged into the fan-in input.
5. Define condition/switch semantics:
   - routing based on structured output/status, not prompt text alone;
   - first-match vs multi-match behavior;
   - default/fallback branch behavior;
   - error branch behavior.
6. Define nonblocking join semantics:
   - join by job id, branch id, node id, or named group;
   - cancellation and retry policy;
   - timeout policy;
   - partial completion policy.
7. Define deterministic end-state aggregation:
   - final graph status must be reproducible from scheduler state and event history;
   - final report should explicitly distinguish success, partial success, failure, cancellation, unresolved conflict, and timeout;
   - aggregation should include changed files, accepted changesets, conflicts, artifacts, reports, test results, and follow-up risks.

