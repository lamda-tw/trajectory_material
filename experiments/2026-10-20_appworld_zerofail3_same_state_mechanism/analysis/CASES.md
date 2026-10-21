# 同状态真实案例

案例按公开的事后选例规则挑出，用于解释统计，不代替全部状态。以下单步展示固定seed20261015；后续表按三个首步seed平均，三种接手策略分别列出。

**2026-10-21核查说明：** 单步示例和后续均值的聚合层级不同，不能把表中三seed平均收益全部归给下方展示的一段seed15代码。此外，实验替换的是完整响应包，叙述文本也进入接手上下文；代码相同不一定等于接手输入相同。终检还发现少量完全相同输入仍产生不同续跑输出，见[最终报告第5.2节](../REPORT.md)。因此这些案例帮助解释可能路径，不逐条证明首步造成了全部收益或损失。

## 最大正向配对差

研究者状态ID：`zerofail3:seed_20261016:396c5a2_2:before_step_04`；在原轨迹第4步之前分叉。

公开任务：Add all the songs from Aria Sterling that have been played over 990 times to my Spotify player queue.

**这个例子说明什么：** 任务要找歌手的歌曲，历史却走向了用户搜索。九个模型在同一历史上的首步如下；ZeroFail3的三个seed都转去取得歌曲/歌手相关规格，Random和Net3仅部分seed如此。这是“更稳定地补充任务相关缺失信息”的具体例子，不代表查一次文档就完成了任务。

| 首步训练seed | Random | Net3 | ZeroFail3 |
| --- | --- | --- | --- |
| 20261015 | 查`search_artists`规格 | 用`Aria`再次搜索用户 | 查`search_artists`规格 |
| 20261016 | 查`search_playlists`规格 | 用`Sterling`再次搜索用户 | 查`search_songs`规格 |
| 20261017 | 重复用完整姓名搜索用户 | 查`search_artists`规格 | 查`search_artists`规格 |

该状态h12在三seed、三接手策略平均后，ZeroFail3比Random高37.04 pp、比Net3高44.44 pp，是事后挑出的最大正例。下面Random与ZeroFail3的seed15代码相同，不能据此解释全部均值差；还要看另两seed、完整文本以及接手分支。该状态没有出现在本次“相同输入输出不一致”审计发现的集合中，但这也不是对所有可能重复运行的确定性保证。

最近一步已执行代码：
```python
search_results = apis.spotify.search_users(query="Aria Sterling")
print(search_results)
```
最近一步反馈摘录：
```text
[
 {
  "first_name": "Stephen",
  "last_name": "Mccoy",
  "email": "stmcco@gmail.com",
  "registered_at": "2022-06-26T18:16:57"
 },
 {
  "first_name": "Laura",
  "last_name": "Mccoy",
  "email": "la-mcco@gmail.com",
  "registered_at": "2022-08-26T18:54:41"
 },
 {
  "first_name": "Chris",
  "last_name": "Mccoy",
  "email": "chris.mcco@gmail.com",
  "registered_at": "2022-02-27T18:54:34"
 },
 {
  "first_name": "Jonathan",
  "last_name": "Ball",
  "email": "jo.ball@gmail.com",
  "registered_at": "2022-05-20T13:23:05"
 },
 {
  "first_name": "Leslie",
  "last_name": "Ball",
  "email": "les_ball@gmail.com",
  "registered_at": "2022-09-18T14:06:32"
 }
]

```

固定前缀机会：A_opportunity=yes（Artist/song identification, play-count filtering, and queue addition require endpoint specifications that have not been supplied. The known user-search specification does not provide these capabilities.）；B_opportunity=yes（A revised name query through search_users can produce new identity evidence or help investigate the unexpected matches. Its complete specification and the actual target name are available, and it requires no authentication. This opportunity is limited to identity investigation; song retrieval and queue modification are not yet ready.）；C_opportunity=no（The task requires complete song coverage, but no relevant song-enumeration pagination or multiple-source specification is known yet. The five returned users and search_users pagination do not establish a missing page of relevant songs.）

### random 的首步

```python
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='search_artists'))
```
实际反馈摘录：
```text
{
 "app_name": "spotify",
 "api_name": "search_artists",
 "path": "/spotify/artists",
 "method": "GET",
 "description": "Search for artists with a query.",
 "parameters": [
  {
   "name": "query",
   "type": "string",
   "required": false,
   "description": "The search query string.",
   "default": "",
   "constraints": []
  },
  {
   "name": "genre",
   "type": "string",
   "required": false,
   "description": "The genre to filter the artists by.",
   "default": null,
   "constraints": []
  },
  {
   "name": "min_follower_count",
   "type": "integer",
   "required": false,
   "description": "The minimum number of followers for search results.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "max_follower_count",
   "type": "integer",
   "required": false,
   "description": "The maximum number of followers for search results.",
   "default": 9223372036854775807,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  },
  {
   "name": "sort_by",
   "type": "string",
   "required": false,
   "description": "The attribute to sort the artists by prefixed with +/- to reflect ascending/descending. Valid attributes: follower_count. If both query and sort_by are 
```
行为判断：relevant_gap_reduced=yes：Obtained the previously missing complete search_artists specification, including artist identifiers, query parameters, pagination, and response fields. This supports a relevant artist lookup, though it does not supply songs or play counts.；grounded_application=no：The executed operation retrieves documentation only; it does not query actual artist or song data, calculate a selection, or modify the queue.；coverage_progress=no：Learning the artist-search pagination specification does not acquire another needed page or source of task data, merge results, or verify song completeness.

### net3 的首步

```python
search_results = apis.spotify.search_users(query="Aria")
print(search_results)
```
实际反馈摘录：
```text
[
 {
  "first_name": "Stephen",
  "last_name": "Mccoy",
  "email": "stmcco@gmail.com",
  "registered_at": "2022-06-26T18:16:57"
 },
 {
  "first_name": "Laura",
  "last_name": "Mccoy",
  "email": "la-mcco@gmail.com",
  "registered_at": "2022-08-26T18:54:41"
 },
 {
  "first_name": "Chris",
  "last_name": "Mccoy",
  "email": "chris.mcco@gmail.com",
  "registered_at": "2022-02-27T18:54:34"
 },
 {
  "first_name": "Jonathan",
  "last_name": "Ball",
  "email": "jo.ball@gmail.com",
  "registered_at": "2022-05-20T13:23:05"
 },
 {
  "first_name": "Leslie",
  "last_name": "Ball",
  "email": "les_ball@gmail.com",
  "registered_at": "2022-09-18T14:06:32"
 }
]

```
行为判断：relevant_gap_reduced=no：The revised user search obtains no new endpoint specification, discovery, or permission information.；grounded_application=yes：Using the available full search_users specification and the target's first name, the candidate tests a broader query. It establishes that this query also returns the same unrelated first-page users, providing limited new evidence about the search mismatch.；coverage_progress=no：Changing the identity-search query does not acquire an additional needed song page, merge sources, or verify song completeness.

### zerofail3 的首步

```python
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='search_artists'))
```
实际反馈摘录：
```text
{
 "app_name": "spotify",
 "api_name": "search_artists",
 "path": "/spotify/artists",
 "method": "GET",
 "description": "Search for artists with a query.",
 "parameters": [
  {
   "name": "query",
   "type": "string",
   "required": false,
   "description": "The search query string.",
   "default": "",
   "constraints": []
  },
  {
   "name": "genre",
   "type": "string",
   "required": false,
   "description": "The genre to filter the artists by.",
   "default": null,
   "constraints": []
  },
  {
   "name": "min_follower_count",
   "type": "integer",
   "required": false,
   "description": "The minimum number of followers for search results.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "max_follower_count",
   "type": "integer",
   "required": false,
   "description": "The maximum number of followers for search results.",
   "default": 9223372036854775807,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  },
  {
   "name": "sort_by",
   "type": "string",
   "required": false,
   "description": "The attribute to sort the artists by prefixed with +/- to reflect ascending/descending. Valid attributes: follower_count. If both query and sort_by are 
```
行为判断：relevant_gap_reduced=yes：Obtained the previously missing complete search_artists specification, including artist identifiers, query parameters, pagination, and response fields. Previously only its endpoint summary was available.；grounded_application=no：The action retrieves documentation only; it does not yet apply the artist-search specification to actual task data or perform a task-related modification.；coverage_progress=no：No artist or song records were acquired, merged, or checked for completeness. Learning pagination parameters is specification discovery, not coverage acquisition.

| 共同接手策略 | Random首步 | Net3首步 | ZeroFail3首步 |
| --- | --- | --- | --- |
| random__seed_20261015 | 5.56% | 0.00% | 33.33% |
| net3__seed_20261015 | 11.11% | 0.00% | 33.33% |
| zerofail3__seed_20261015 | 33.33% | 27.78% | 94.44% |

表中是有限12步内、该状态上的官方检查通过比例，并非整题自然rollout成功率。代码/反馈长时只展示摘录，完整证据见results与analysis。

## 最小/负向配对差

**解释限制：** 该状态也是终检发现“完全相同接手输入、权重和seed，却产生不同输出”的状态之一。组均值中ZeroFail3相对Random/Net3均为−7.41 pp，但不能把这个负差全部解释成ZeroFail3首步更差。下方seed15三组都读取相同的supervisor接口列表；要区分首步内容与生成运行变动，需要额外受控复现，本轮没有重抽或替换原结果。

研究者状态ID：`net3:seed_20261015:b119b1f_1:before_step_04`；在原轨迹第4步之前分叉。

公开任务：Keep going to the previous song on Spotify until you reach a song by Luna Starlight.

最近一步已执行代码：
```python
print(apis.api_docs.show_api_descriptions(app_name='spotify'))
```
最近一步反馈摘录：
```text
[
 {
  "name": "show_account",
  "description": "Show your account information. Unlike show_profile, this includes private information."
 },
 {
  "name": "signup",
  "description": "Sign up to create account."
 },
 {
  "name": "delete_account",
  "description": "Delete your account."
 },
 {
  "name": "update_account_name",
  "description": "Update your first or last name in the account profile."
 },
 {
  "name": "login",
  "description": "Login to your account."
 },
 {
  "name": "logout",
  "description": "Logout from your account."
 },
 {
  "name": "send_verification_code",
  "description": "Send account verification code to your email address."
 },
 {
  "name": "verify_account",
  "description": "Verify your account using the verification code sent to your email address."
 },
 {
  "name": "send_password_reset_code",
  "description": "Send password reset code to your email address."
 },
 {
  "name": "reset_password",
  "description": "Reset your password using the password reset code sent to your email address."
 },
 {
  "name": "show_profile",
  "description": "Show public profile information of a user."
 },
 {
  "name": "search_users",
  "description": "Search users by name or email address."
 },
 {
  "name": "show_genres",
  "description": "Show the list of all music genres."
 },
 {
  "name": "search_songs",
  "description": "Search for songs with a query."
 },
 {
  "name": "show_song",
  "description": "Get details of a specific song."
 },
 {
  "name": "show_song_privates",
  "description": "Show information about the song that is private to the user."
 },
 {
  "name": "like_song",
  "description": "Like a song."
 },
 {
  "name": "unlike_song",
  "description": "Unlike a song."
 },
 {
  "name": "show_liked_songs",
  "description": "Get a list of songs you have liked."
 },
 {
  "name": "search_albums",
  "description": "Search for albums with a query."
 },
 {
  "name": "show_album",
  "description": "Get details of a specific album."
 },
 {
  "name": "show_album_privates",
  "description": "Show information about the album that is private to the user."
 },
 {
  "name": "like_album",
  "description": "Like a album."
 },
 {
  "name": "unlike_album",
  "descrip
```

固定前缀机会：A_opportunity=yes（Necessary credential-retrieval, backward-navigation, and artist-inspection specifications are missing. Their endpoint names are already discoverable from the supplied summaries.）；B_opportunity=no（No task-evidence query or playback operation is established as executable with both a known full specification and actual required inputs. Login lacks an actual password; playback and credential retrieval lack full specifications. Documentation discovery remains available, but does not itself establish new playback evidence.）；C_opportunity=no（The task requires a sequential artist-based stopping condition, not a complete library enumeration or global comparison. The known playlist pagination specification does not create a relevant coverage obligation.）

### random 的首步

```python
print(apis.api_docs.show_api_descriptions(app_name='supervisor'))
```
实际反馈摘录：
```text
[
 {
  "name": "show_active_task",
  "description": "Show the currently active task assigned to you by the supervisor."
 },
 {
  "name": "complete_task",
  "description": "Mark the currently active task as complete with the given answer."
 },
 {
  "name": "show_profile",
  "description": "Show your supervisor's profile information."
 },
 {
  "name": "show_addresses",
  "description": "Show your supervisor's addresses."
 },
 {
  "name": "show_payment_cards",
  "description": "Show your supervisor's payment_cards."
 },
 {
  "name": "show_account_passwords",
  "description": "Show your supervisor's app account passwords."
 }
]

```
行为判断：relevant_gap_reduced=no：The Supervisor endpoint list was already obtained in step 2. The repeated list supplies no missing full specification, credentials, or playback information.；grounded_application=no：The candidate only rereads documentation. It does not use actual credentials or playback data to obtain new task evidence or produce a task-related effect.；coverage_progress=no：No additional playback source, necessary page, merge, or completeness verification is executed.

### net3 的首步

```python
print(apis.api_docs.show_api_descriptions(app_name='supervisor'))
```
实际反馈摘录：
```text
[
 {
  "name": "show_active_task",
  "description": "Show the currently active task assigned to you by the supervisor."
 },
 {
  "name": "complete_task",
  "description": "Mark the currently active task as complete with the given answer."
 },
 {
  "name": "show_profile",
  "description": "Show your supervisor's profile information."
 },
 {
  "name": "show_addresses",
  "description": "Show your supervisor's addresses."
 },
 {
  "name": "show_payment_cards",
  "description": "Show your supervisor's payment_cards."
 },
 {
  "name": "show_account_passwords",
  "description": "Show your supervisor's app account passwords."
 }
]

```
行为判断：relevant_gap_reduced=no：The Supervisor endpoint list was already obtained in step 2. The repeated list supplies no missing full specification, credentials, or playback information.；grounded_application=no：The candidate only rereads documentation. It does not use actual credentials or playback data to obtain new task evidence or produce a task-related effect.；coverage_progress=no：No additional playback source, necessary page, merge, or completeness verification is executed.

### zerofail3 的首步

```python
print(apis.api_docs.show_api_descriptions(app_name='supervisor'))
```
实际反馈摘录：
```text
[
 {
  "name": "show_active_task",
  "description": "Show the currently active task assigned to you by the supervisor."
 },
 {
  "name": "complete_task",
  "description": "Mark the currently active task as complete with the given answer."
 },
 {
  "name": "show_profile",
  "description": "Show your supervisor's profile information."
 },
 {
  "name": "show_addresses",
  "description": "Show your supervisor's addresses."
 },
 {
  "name": "show_payment_cards",
  "description": "Show your supervisor's payment_cards."
 },
 {
  "name": "show_account_passwords",
  "description": "Show your supervisor's app account passwords."
 }
]

```
行为判断：relevant_gap_reduced=no：The Supervisor endpoint list was already obtained in step 2. The repeated list supplies no missing full specification, credentials, or playback information.；grounded_application=no：The candidate only rereads documentation. It does not use actual credentials or playback data to obtain new task evidence or produce a task-related effect.；coverage_progress=no：No additional playback source, necessary page, merge, or completeness verification is executed.

| 共同接手策略 | Random首步 | Net3首步 | ZeroFail3首步 |
| --- | --- | --- | --- |
| random__seed_20261015 | 0.00% | 0.00% | 0.00% |
| net3__seed_20261015 | 0.00% | 0.00% | 0.00% |
| zerofail3__seed_20261015 | 66.67% | 66.67% | 44.44% |

表中是有限12步内、该状态上的官方检查通过比例，并非整题自然rollout成功率。代码/反馈长时只展示摘录，完整证据见results与analysis。

## 旧发现复查（单独解释）

这个预选复查状态的h12组均值持平；两条旧发现复查状态合在一起，三组检查Macro也都为54.63%。因此旧发现没有在这个小型复查集合中表现出平均组间优势，不能把它当成普遍机制的重复验证。

研究者状态ID：`net3:seed_20261015:d4e9306_2:before_step_38`；在原轨迹第38步之前分叉。

公开任务：Follow artists of all the songs and albums I have ever liked on Spotify.

最近一步已执行代码：
```python
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='show_liked_songs'))
```
最近一步反馈摘录：
```text
{
 "app_name": "spotify",
 "api_name": "show_liked_songs",
 "path": "/spotify/liked_songs",
 "method": "GET",
 "description": "Get a list of songs you have liked.",
 "parameters": [
  {
   "name": "access_token",
   "type": "string",
   "required": true,
   "description": "Access token obtained from spotify app login.",
   "default": null,
   "constraints": []
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  },
  {
   "name": "sort_by",
   "type": "string",
   "required": false,
   "description": "The attribute to sort the liked songs by prefixed with +/- to reflect ascending/descending. Valid attributes: liked_at, play_count and title.",
   "default": "-liked_at",
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": [
   {
    "song_id": 1,
    "title": "string",
    "album_id": 1,
    "album_title": "string",
    "duration": 1,
    "artists": [
     {
      "id": 1,
      "name": "string"
     }
    ],
    "liked_at": "2019-01-01T00:00:00"
   }
  ],
  "failure": {
   "message": "string"
  }
 }
}

```

固定前缀机会：A_opportunity=yes（Credential retrieval is a concrete prerequisite for both liked-item sources, and its full Supervisor endpoint specification is missing. The login, liked-item, and follow specifications are already known and do not need repeated discovery.）；B_opportunity=no（No actual access token, liked-item objects, or target artist IDs are available for a substantive task query, calculation, or follow operation. The ready documentation lookups address specification discovery; an unfiltered public artist search would not establish which artists belong to this account's liked items.）；C_opportunity=yes（The task requires coverage of two known paginated sources, but neither source has yielded any actual records or an exhaustion result. Sequential retrieval through an empty page for each source, with all preceding pages retained, would provide a visible end condition; no cached complete dataset or account-level summary is supplied.）

### random 的首步

```python
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='show_liked_albums'))
```
实际反馈摘录：
```text
{
 "app_name": "spotify",
 "api_name": "show_liked_albums",
 "path": "/spotify/liked_albums",
 "method": "GET",
 "description": "Get a list of albums you have liked.",
 "parameters": [
  {
   "name": "access_token",
   "type": "string",
   "required": true,
   "description": "Access token obtained from spotify app login.",
   "default": null,
   "constraints": []
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  },
  {
   "name": "sort_by",
   "type": "string",
   "required": false,
   "description": "The attribute to sort the liked albums by prefixed with +/- to reflect ascending/descending. Valid attributes: liked_at and title.",
   "default": "-liked_at",
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": [
   {
    "album_id": 1,
    "title": "string",
    "genre": "string",
    "artists": [
     {
      "id": 1,
      "name": "string"
     }
    ],
    "rating": 0.0,
    "like_count": 1,
    "review_count": 1,
    "release_date": "2019-01-01T00:00:00",
    "song_ids": [
     1
    ],
    "liked_at": "2019-01-01T00:00:00"
   }
  ],
  "failure": {
   "message": "string"
  }
 }
}

```
行为判断：relevant_gap_reduced=no：The liked-albums full specification was already available repeatedly, most recently at step 34. This reread supplies no missing endpoint, specification, or permission information.；grounded_application=no：The action retrieves documentation only. It does not apply the known specification to actual account data or obtain a task-related local effect.；coverage_progress=no：No liked-item page, merge, deduplication, or completeness verification executes.

### net3 的首步

```python
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='show_liked_albums'))
```
实际反馈摘录：
```text
{
 "app_name": "spotify",
 "api_name": "show_liked_albums",
 "path": "/spotify/liked_albums",
 "method": "GET",
 "description": "Get a list of albums you have liked.",
 "parameters": [
  {
   "name": "access_token",
   "type": "string",
   "required": true,
   "description": "Access token obtained from spotify app login.",
   "default": null,
   "constraints": []
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  },
  {
   "name": "sort_by",
   "type": "string",
   "required": false,
   "description": "The attribute to sort the liked albums by prefixed with +/- to reflect ascending/descending. Valid attributes: liked_at and title.",
   "default": "-liked_at",
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": [
   {
    "album_id": 1,
    "title": "string",
    "genre": "string",
    "artists": [
     {
      "id": 1,
      "name": "string"
     }
    ],
    "rating": 0.0,
    "like_count": 1,
    "review_count": 1,
    "release_date": "2019-01-01T00:00:00",
    "song_ids": [
     1
    ],
    "liked_at": "2019-01-01T00:00:00"
   }
  ],
  "failure": {
   "message": "string"
  }
 }
}

```
行为判断：relevant_gap_reduced=no：The liked-albums full specification was already available repeatedly, most recently at step 34. This reread supplies no missing endpoint, specification, or permission information.；grounded_application=no：The action retrieves documentation only. It does not apply the known specification to actual account data or obtain a task-related local effect.；coverage_progress=no：No liked-item page, merge, deduplication, or completeness verification executes.

### zerofail3 的首步

```python
print(apis.api_docs.show_api_doc(app_name='spotify', api_name='show_liked_albums'))
```
实际反馈摘录：
```text
{
 "app_name": "spotify",
 "api_name": "show_liked_albums",
 "path": "/spotify/liked_albums",
 "method": "GET",
 "description": "Get a list of albums you have liked.",
 "parameters": [
  {
   "name": "access_token",
   "type": "string",
   "required": true,
   "description": "Access token obtained from spotify app login.",
   "default": null,
   "constraints": []
  },
  {
   "name": "page_index",
   "type": "integer",
   "required": false,
   "description": "The index of the page to return.",
   "default": 0,
   "constraints": [
    "value >= 0"
   ]
  },
  {
   "name": "page_limit",
   "type": "integer",
   "required": false,
   "description": "The maximum number of results to return per page.",
   "default": 5,
   "constraints": [
    "value >= 1, <= 20"
   ]
  },
  {
   "name": "sort_by",
   "type": "string",
   "required": false,
   "description": "The attribute to sort the liked albums by prefixed with +/- to reflect ascending/descending. Valid attributes: liked_at and title.",
   "default": "-liked_at",
   "constraints": []
  }
 ],
 "response_schemas": {
  "success": [
   {
    "album_id": 1,
    "title": "string",
    "genre": "string",
    "artists": [
     {
      "id": 1,
      "name": "string"
     }
    ],
    "rating": 0.0,
    "like_count": 1,
    "review_count": 1,
    "release_date": "2019-01-01T00:00:00",
    "song_ids": [
     1
    ],
    "liked_at": "2019-01-01T00:00:00"
   }
  ],
  "failure": {
   "message": "string"
  }
 }
}

```
行为判断：relevant_gap_reduced=no：The liked-albums full specification was already available repeatedly, most recently at step 34. This reread supplies no missing endpoint, specification, or permission information.；grounded_application=no：The action retrieves documentation only. It does not apply the known specification to actual account data or obtain a task-related local effect.；coverage_progress=no：No liked-item page, merge, deduplication, or completeness verification executes.

| 共同接手策略 | Random首步 | Net3首步 | ZeroFail3首步 |
| --- | --- | --- | --- |
| random__seed_20261015 | 16.67% | 16.67% | 16.67% |
| net3__seed_20261015 | 16.67% | 16.67% | 16.67% |
| zerofail3__seed_20261015 | 16.67% | 16.67% | 16.67% |

表中是有限12步内、该状态上的官方检查通过比例，并非整题自然rollout成功率。代码/反馈长时只展示摘录，完整证据见results与analysis。
