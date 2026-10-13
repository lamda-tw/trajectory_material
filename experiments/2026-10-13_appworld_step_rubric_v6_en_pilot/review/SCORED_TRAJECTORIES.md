# 英文评分轨迹结果

仅展示已保存的有效输出；原始请求、所有无效尝试和重复结果见 runs/。

## development

### 302c169_2__02

 I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Missing authorization caused 401; API spec unchecked. |
| 2 | FNPNNUNF | Recovery called a nonexistent, undocumented API. |
| 3 | PPPNNPNF | Supervisor API was called without checking its spec. |
| 4 | FNFNNNNF | Email was used where login required a phone number. |
| 5 | PPPNNPNP |  |
| 6 | PNPNNPNP |  |
| 7 | PPPNNNNF | show_alarms spec was not checked before use. |
| 8 | PPPPNNNP |  |
| 9 | PPPPNNNP |  |
| 10 | PPPPPNNF | update_alarm spec was not checked before writes. |
| 11 | PNPNNNPF | complete_task spec was not checked before submission. |

### 302c169_3__02

 I am going on a vacation. Move my go-to-sleep phone alarm to 20 minutes later and disable the rest.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API call failed; specification was not checked. |
| 2 | PPPNNPNP |  |
| 3 | FNPNNPNF | Alarm read lacked authentication and a checked spec. |
| 4 | PPPNNFNP | Repeated API descriptions already showed the login API. |
| 5 | FPNNNPNF | Credential parsing failed; API specs were not checked. |
| 6 | FPPNNFNF | Login lacked username; credential query was repeated. |
| 7 | PPPNNPNP |  |
| 8 | PPPNNFNF | Credential query was repeated; its spec was unchecked. |
| 9 | PUPNNPNF | Alarm-list completeness is unknown; its spec was unchecked. |
| 10 | PFFFNNNP | Wake Up was unsupported as the go-to-sleep alarm. |
| 11 | PFFFFNNF | Wrong alarm and time basis; update spec was unchecked. |
| 12 | PNFNNNFF | Claimed completion after incorrect alarm edits. |

### 60d0b5b_1__02

 The last Venmo payment request I sent to Robert was an accident and they approved it. Send them the money back.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPNNNFNP | Repeated the same API listing without new need. |
| 3 | PPNNNPNP |  |
| 4 | PPNNNFNP | Repeated the same API document without new need. |
| 5 | PPNNNFNP | Repeated the same API document without new need. |
| 6 | PPNNNFNP | Repeated the same API document without new need. |
| 7 | FNNPNNNP | venmo_access_token was undefined. |
| 8 | PPNNNPNP |  |
| 9 | FNNNNPNF | Bad list comprehension caused TypeError; API spec unchecked. |
| 10 | PPPNNPNF | Supervisor API was used without checking its specification. |
| 11 | PNPNNNNP |  |
| 12 | PUPPNPNF | Only the first page was read despite mandatory pagination. |
| 13 | PUFFNNNF | Selected the oldest shown request; extra code blocks. |
| 14 | PPFNNFNF | Misstated the oldest as latest; extra code blocks. |
| 15 | PPFNNPNP | Request 3228 was still misidentified as the latest. |
| 16 | PPPNNFNP | Repeated the API listing without new need. |
| 17 | FNFFNNNP | Tried deleting the oldest request as a refund; got 422. |
| 18 | PNNFNFPF | Missed send-money API; complete_task spec unchecked. |

### 60d0b5b_2__03

 The last Venmo payment request I sent to Cory was an accident and they approved it. Send them the money back.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PNNNNNNP |  |
| 2 | PNNNNNNP |  |
| 3 | FNNNNNNP | venmo_access_token was undefined. |
| 4 | FNNNNUNF | Recovery failed before credentials; login spec unchecked. |
| 5 | PPNNNPNF | Password API spec was not checked. |
| 6 | FNPNNPNF | Boolean credential filter failed; login spec unchecked. |
| 7 | PPPNNPNF | Venmo login spec was not checked. |
| 8 | PFPNNNNF | Only the first request page was read. |
| 9 | FNFNNNNF | It inferred no Cory request from one page. |
| 10 | FNPNNPNF | Phone API spec was unchecked; authentication failed. |
| 11 | FNPNNUNF | Recovery failed before login; its spec was unchecked. |
| 12 | FNPNNPNF | Phone login failed and its API spec was unchecked. |
| 13 | PPPNNPNP |  |
| 14 | FNPNNFNF | It repeated the same known-invalid login. |
| 15 | FNPNNUNF | Undocumented profile call used invalid arguments. |
| 16 | PPPNNPNF | Phone profile API spec was not checked. |
| 17 | PNPNNPNF | Phone login API spec was not checked. |
| 18 | PUPNNNNF | Unread contact pages leave Cory uniqueness uncertain. |
| 19 | PUPUNNNF | Unread contacts made Cory ambiguous; extra code blocks. |
| 20 | PFFNNNNF | It fabricated searches and queried Susan's request. |
| 21 | PUPNNPNF | Unread pages may contain later approved Cory requests. |
| 22 | PFFFNNFF | It fabricated refunds and retrieved Nancy's requests. |
| 23 | PFFFNFFF | It used Nancy's amount and falsely claimed completion. |
| 24 | FNFFNFFF | It used the wrong request and an unavailable refund API. |
| 25 | PNPNNPNP |  |
| 26 | PNPNNFNP | It repeated the same API-list query without need. |
| 27 | FNFFNFFF | Its workaround could not refund Cory and was not executed. |
| 28 | FNFFNFFF | Approve-then-deny cannot refund Cory; the call failed. |
| 29 | FNFFNUFF | It assumed request ID was a transaction ID; read failed. |
| 30 | FNFFNPFF | Wrong-target search failed on invalid Unicode surrogates. |
| 31 | PUFFNPFF | It fabricated a match; unread results remained. |
| 32 | PFFFNPFF | ID search was unsupported and returned unrelated records. |
| 33 | PFFFNFFF | It repeated a known-useless query and fabricated success. |
| 34 | PFFFNFFF | It repeated a known-useless query and fabricated success. |
| 35 | PFFFNFFF | It repeated a known-useless query and fabricated success. |
| 36 | PFFFNFFF | It repeated a known-useless query and fabricated success. |
| 37 | PFFFNFFF | It repeated a known-useless query and fabricated success. |
| 38 | PFFFNFNF | It repeated a known-useless query and fabricated a match. |

### 76f2c72_1__03

 What is the total cost of my electricity bills for this year? The bills are in "~/bills/" directory of my file system.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PNNNNNNP |  |
| 2 | FNNNNNNF | show_directory lacked a prior spec lookup and returned 401. |
| 3 | PNNNNFNP | It repeated an already sufficient API listing. |
| 4 | FPPNNPNF | Login omitted the required username and returned 422. |
| 5 | PNNNNPNP |  |
| 6 | FNNNNPNF | The nonexistent API call failed to recover the username. |
| 7 | PNNNNPNP |  |
| 8 | PPPNNPNF | show_profile was called without a prior spec lookup. |
| 9 | PNPNNPNP |  |
| 10 | PPPNNNNF | show_directory was used without a prior spec lookup. |
| 11 | PPPPNNNP |  |
| 12 | PPUFNNNF | The current year was assumed without obtaining the date. |
| 13 | PUNNNNNF | The 2023-05 PDF was skipped, leaving coverage unclear. |
| 14 | FNNFNNNF | Parsing failed, and the annual-selection rule omitted PDFs. |
| 15 | PUPFNPNF | The sum excluded the unread 2023-05 PDF. |
| 16 | PNUFNNUF | The unread 2023-05 bill leaves 368.0 unestablished. |

### 7d7fbf6_1__00

 The "~/photographs/" directory in my file system has photo files organized in sub-directories for each vacation spot. Compress them and save them in "~/photographs/vacations/<vacation_spot>.zip" for each vacation spot, and then delete all vacation spot sub-directories. Here, <vacation_spot> is the name of the vacation spot as it appears in the sub-directory name.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API call lacked the required specification lookup. |
| 2 | PPPNNPNP |  |
| 3 | FNPNNPNF | Unauthorized call lacked its full API specification. |
| 4 | FNPNNPNF | Login omitted credentials and its specification lookup. |
| 5 | PPPNNPNF | Password API was used without its full specification. |
| 6 | PPPNNPNF | File-system login lacked a prior full API lookup. |
| 7 | FNPNNFNF | Repeated the unauthorized read without passing the token. |
| 8 | PPPNNPNF | Directory API was used without its full specification. |
| 9 | PPPNNNNF | Directory API was used without its full specification. |
| 10 | FNFFNNNF | Empty spot names and an invalid, undocumented parameter. |
| 11 | PPPNNPNP |  |
| 12 | FNFFNPNP | Spot extraction and archive destination were wrong. |
| 13 | FNFFFFNF | Wrong archive path; failed compound write was retried. |
| 14 | PPPNNPNF | Undocumented API call plus an extra commentary code block. |
| 15 | PPPNNPNF | Directory APIs lacked full specification lookups. |
| 16 | PPFFFPNF | Archives went outside vacations; extra code block. |
| 17 | FNFNNNFF | False completion claim; complete_task was never called. |

### b0a8eae_3__03

 Start playing a playlist on Spotify that has enough songs for my workout today. I do not want to have to change the playlist in the middle of my workout. The workout plan is in Simple Note.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNFNNNNF | It guessed a title and called a nonexistent API. |
| 2 | PPPNNPNP |  |
| 3 | FNNNNPNF | Search lacked authentication and prior API docs. |
| 4 | PPPNNFNP | It repeated discovery although login was already listed. |
| 5 | PPPNNPNF | Credential and login APIs lacked specification checks. |
| 6 | FNPNNFNF | It repeated the search without passing the new token. |
| 7 | PPPNNPNF | search_notes lacked a prior API specification check. |
| 8 | PPPNNNNF | show_note lacked a prior API specification check. |
| 9 | PNPFNNNP | It summed the whole week instead of today's workout. |
| 10 | FNPNNNNP | spotify_access_token was undefined. |
| 11 | PPPNNPNF | The credential API lacked a prior specification check. |
| 12 | PPPNNPNP |  |
| 13 | PFFFNNNF | It invented a KeyError and equated minutes with songs. |
| 14 | PPFNNFNP | It handled a KeyError that never occurred. |
| 15 | PPPFNPNP | It aggregated all playlists instead of each playlist. |
| 16 | PFPFNPNP | Song count cannot establish coverage of 315 minutes. |
| 17 | PNFFNFNP | It asserted 315 songs were required without support. |
| 18 | PFFFNFNP | It repeated the unsupported song-count test unchanged. |
| 19 | PFFFNFNP | It repeated the unsupported song-count test unchanged. |
| 20 | PFFFNFNP | It repeated the unsupported song-count test unchanged. |
| 21 | PFFFNFNP | It repeated the unsupported song-count test unchanged. |
| 22 | PFFFNFNP | It repeated the unsupported song-count test unchanged. |
| 23 | PFFFNFNP | It repeated the unsupported song-count test unchanged. |
| 24 | PFFFNFNP | It repeated the unsupported song-count test unchanged. |
| 25 | PPFFNFNP | It chose a playlist not shown to last through the workout. |
| 26 | FNPFNNNF | The API did not exist, and the playlist choice was flawed. |
| 27 | PPPNNPNP |  |
| 28 | PNPFUPNF | Duration was unknown, and play_music lacked API docs. |
| 29 | PNUNNNUF | Sufficiency was unknown; complete_task lacked API docs. |

### b7a9ee9_1__05

 Follow all artists of all classical-genre songs in any of my playlists on Spotify.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords caused a NameError. |
| 2 | PPNNNPNF | Password API was used without its specification. |
| 3 | PPPNNPNP |  |
| 4 | PPPNNNNP |  |
| 5 | PFFNNNNF | Playlist objects were misparsed; API was undocumented. |
| 6 | FNFPNNNP | String entries failed; the 80-song claim was false. |
| 7 | PPFNNPNP | It called a list of strings a string and playlist objects. |
| 8 | FNFNNPNF | Song IDs were misdescribed; undocumented API failed. |
| 9 | PPPNNPNP |  |
| 10 | FNPNNPNF | show_song was called before checking its specification. |
| 11 | PPPNNPNP |  |
| 12 | FNPNNPNF | Undocumented show_playlist preceded the type error. |
| 13 | PPNNNPNP |  |
| 14 | PPPNNPNP |  |
| 15 | PPPNNPNF | show_playlist was used without its specification. |
| 16 | PPPPNNNP |  |
| 17 | PPPNNNNF | Commentary ended with an unclosed code fence. |
| 18 | FNPFNNNF | Duplicate targets and missing auth made the attempt fail. |
| 19 | PPPNNPNP |  |
| 20 | FNPFNPNP | Blind following hit an already-followed artist. |
| 21 | FUFPNPNF | Wrong field and incomplete coverage caused a KeyError. |
| 22 | PPPNNPNP |  |
| 23 | FUPFPFNF | Duplicate retry followed two artists, then failed. |
| 24 | PPNNNPNP |  |
| 25 | PPPPPPNF | Following API was used without its specification. |
| 26 | PNPNNNPF | complete_task was called without checking its specification. |

### cf6abd2_2__01

 Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPNNNNNP |  |
| 3 | FNNNNNNF | Unauthenticated call failed; API spec was not checked. |
| 4 | FNPNNPNF | Login lacked required fields and its spec was not checked. |
| 5 | PPNNNPNF | API used without required specification lookup. |
| 6 | FNPNNPNF | Called a nonexistent, undocumented supervisor API. |
| 7 | FNPNNPNF | Called a nonexistent, undocumented supervisor API. |
| 8 | PPPNNPNF | API used without required specification lookup. |
| 9 | PNPFNPNF | Email was assumed to be the account username. |
| 10 | PPPNNPNF | API used without required specification lookup. |
| 11 | PPPNNPNF | API used without required specification lookup. |
| 12 | PPPNNFNF | Identical search was repeated without new information. |
| 13 | PPPNNPNF | API used without required specification lookup. |
| 14 | PPPNNPNF | API used without required specification lookup. |
| 15 | PPPPNNNF | API used without required specification lookup. |
| 16 | PPPPPNNF | API used without required specification lookup. |
| 17 | PNPNNNPF | Completion API spec was not checked before use. |

### e7a10f8_1__05

 How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords caused a NameError. |
| 2 | PPNNNPNF | Supervisor API specification was not checked. |
| 3 | PPPNNPNP |  |
| 4 | PUNNNNNF | Pagination was skipped, so full coverage is unknown. |
| 5 | FPFUNNNF | Used nonexistent song_ids and an unchecked API. |
| 6 | PPNNNPNP |  |
| 7 | PUUUNPNP | Library coverage and duration units remain unknown. |
| 8 | PNNNNFNP | Repeated the same value expression without new need. |
| 9 | PNNNNFNP | Repeated the same value expression without new need. |
| 10 | PNNNNFNP | Repeated the same value expression without new need. |
| 11 | PNNNNFNP | Repeated the same value expression without new need. |
| 12 | PNNNNFNP | Repeated the same value expression without new need. |
| 13 | PNNNNFNP | Repeated the same value expression without new need. |
| 14 | PNNNNFNP | Repeated the same value expression without new need. |
| 15 | PNNNNFNP | Repeated the same value expression without new need. |
| 16 | PNNNNFNP | Repeated the same value expression without new need. |
| 17 | PNNNNFNP | Repeated the same value expression without new need. |
| 18 | PNNNNFNP | Repeated the same value expression without new need. |
| 19 | PNNNNFNP | Repeated the same value expression without new need. |
| 20 | PNNNNFNP | Repeated the same value expression without new need. |
| 21 | PNNNNFNP | Repeated the same value expression without new need. |
| 22 | PNNNNFNP | Repeated the same value expression without new need. |
| 23 | PNNNNFNP | Repeated the same value expression without new need. |
| 24 | PNNNNFNP | Repeated the same value expression without new need. |
| 25 | PNNNNFNP | Repeated the same value expression without new need. |
| 26 | PNNNNFNP | Repeated the same value expression without new need. |
| 27 | PNNNNFNP | Repeated the same value expression without new need. |
| 28 | PNNNNFNP | Repeated the same value expression without new need. |
| 29 | PNNNNFNP | Repeated the same value expression without new need. |
| 30 | PNNNNFNP | Repeated the same value expression without new need. |
| 31 | PNNNNFNP | Repeated the same value expression without new need. |
| 32 | PNNNNFNP | Repeated the same value expression without new need. |
| 33 | PNNNNFNP | Repeated the same value expression without new need. |
| 34 | PNNNNFNP | Repeated the same value expression without new need. |
| 35 | PNNNNFNP | Repeated the same value expression without new need. |
| 36 | PNNNNFNP | Repeated the same value expression without new need. |
| 37 | PNNNNFNP | Repeated the same value expression without new need. |
| 38 | PNNNNFNP | Repeated the same value expression without new need. |
| 39 | PNNNNFNP | Repeated the same value expression without new need. |
| 40 | PNNNNFNP | Repeated the same value expression without new need. |
| 41 | PNNNNFNP | Repeated the same value expression without new need. |
| 42 | PNNNNFNP | Repeated the same value expression without new need. |
| 43 | PNNNNFNP | Repeated the same value expression without new need. |
| 44 | PNNNNFNP | Repeated the same value expression without new need. |
| 45 | PNNNNFNP | Repeated the same value expression without new need. |
| 46 | PNNNNFNP | Repeated the same value expression without new need. |
| 47 | PNNNNFNP | Repeated the same value expression without new need. |
| 48 | PNNNNFNP | Repeated the same value expression without new need. |
| 49 | PNNNNFNP | Repeated the same value expression without new need. |
| 50 | PNNNNFFF | Repeated output; no answer or complete_task was delivered. |

### e7a10f8_2__02

 How long is my shortest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords caused NameError. |
| 2 | PPNNNPNF | Password API specs were not checked. |
| 3 | PPPNNPNP |  |
| 4 | PNPNNPNP |  |
| 5 | PPPNNNNP |  |
| 6 | PPPNNNNF | show_playlist specs were not checked. |
| 7 | FNFFNNNP | Used nonexistent song_ids and duration_ms fields. |
| 8 | PPPNNPNP |  |
| 9 | PPFFNPNP | Assumed milliseconds, yielding incorrect zero durations. |
| 10 | PPFFNFNP | Repeated the same incorrect millisecond conversion. |
| 11 | PPPNNPNP |  |
| 12 | PPFFNFNP | Repeated the same incorrect millisecond conversion. |
| 13 | PPFFNPNP | Misidentified the duration sum as milliseconds. |
| 14 | PPFFNFNP | Repeated known output and kept the unsupported unit. |
| 15 | PPFNNFNP | Repeated a known value and mislabeled its unit. |
| 16 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 17 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 18 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 19 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 20 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 21 | PPFNNFNP | Repeated a known value and mislabeled its unit. |
| 22 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 23 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 24 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 25 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 26 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 27 | PPFNNFNP | Repeated a known value and mislabeled its unit. |
| 28 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 29 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 30 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 31 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 32 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 33 | PPFNNFNP | Repeated a known value and mislabeled its unit. |
| 34 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 35 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 36 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 37 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 38 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 39 | PPFNNFNP | Repeated a known value and mislabeled its unit. |
| 40 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 41 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 42 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 43 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 44 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 45 | PPFNNFNP | Repeated a known value and mislabeled its unit. |
| 46 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 47 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 48 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 49 | PPFFNFNP | Repeated conversions using an unsupported unit. |
| 50 | PPFFNFNP | Repeated conversions using an unsupported unit. |

### e7a10f8_3__04

 How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNFFNNNF | Invalid API; the plan invents a 3-minute song length. |
| 2 | PPPNNPNF | API specification was not checked before use. |
| 3 | PNPNNNNP |  |
| 4 | PUPNNNNF | Only the default page was read, so coverage is unknown. |
| 5 | PUPFNNNP | Song count does not establish the longest duration. |
| 6 | PNFFNNNP | The 3-minute average is invented, so 24 is unsupported. |
| 7 | PNFFNNFF | Submitted 24 without song durations or required API docs. |

## development_r1

### 302c169_2__02

 I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unauthorized call; API spec not checked. |
| 2 | FNNNNFNF | Unknown API; auth error remained. |
| 3 | PPPNNPNF | Password API spec was not checked. |
| 4 | FNFNNNNF | Email used where phone number was required. |
| 5 | PPNNNPNP |  |
| 6 | PNPNNPNP |  |
| 7 | PPNNNNNF | Alarm-list API spec was not checked. |
| 8 | PPPPNNNP |  |
| 9 | PNPPNNNP |  |
| 10 | PNPPPNNF | Alarm-update API spec was not checked. |
| 11 | PNPNNNPF | complete_task spec was not checked. |

### 302c169_3__02

 I am going on a vacation. Move my go-to-sleep phone alarm to 20 minutes later and disable the rest.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API; no specification checked. |
| 2 | PPNNNPNP |  |
| 3 | FNNNNPNF | Missing token; API spec was not checked. |
| 4 | PPNNNFNP | Repeated the same API listing without need. |
| 5 | FPFNNPNF | Boolean was subscripted; APIs undocumented. |
| 6 | FPPNNPNF | Username missing; APIs not yet specified. |
| 7 | PPNNNPNP |  |
| 8 | PPPNNFNF | Repeated password read; its API undocumented. |
| 9 | PUPNNPNF | Alarm-list coverage unknown; API undocumented. |
| 10 | PFFFNNNP | Wake Up was assumed to mean go-to-sleep. |
| 11 | PFFFFNNF | Used now, and changed an unsupported alarm. |
| 12 | PNFNNNFF | Claimed success after wrong edits; API undocumented. |

### 60d0b5b_1__02

 The last Venmo payment request I sent to Robert was an accident and they approved it. Send them the money back.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PFNNNFNP | Repeated API list instead of retrieving data. |
| 3 | PPNNNNNP |  |
| 4 | PFNNNFNP | Repeated the same documentation query. |
| 5 | PFNNNFNP | Repeated the same documentation query. |
| 6 | PFNNNFNP | Repeated the same documentation query. |
| 7 | FNNNNNNF | Undefined token; execution raised NameError. |
| 8 | PPNNNPNP |  |
| 9 | FPNNNPNF | Bad list comprehension caused TypeError. |
| 10 | PPPNNPNF | Supervisor API specs were never checked. |
| 11 | PNPNNNNP |  |
| 12 | PUPNNPNF | Pagination omitted; later records are unknown. |
| 13 | PUFFNNNF | Selected oldest item; extra code blocks. |
| 14 | PPFNNFNF | False last-ID claim; many extra code blocks. |
| 15 | PPNNNNNP |  |
| 16 | PPPNNFNP | Repeated API list without new information. |
| 17 | FNFFNNNP | Delete cannot refund a completed request. |
| 18 | PNPFNFPF | Ignored send-money option; docs unchecked. |

### 60d0b5b_2__03

 The last Venmo payment request I sent to Cory was an accident and they approved it. Send them the money back.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPNNNNNP |  |
| 3 | FNNNNNNP | Undefined access token caused NameError. |
| 4 | FNNNNPNF | Used undefined passwords; login spec unchecked. |
| 5 | PPNNNPNF | Supervisor API spec was not checked. |
| 6 | FNPNNNNF | Boolean indexing caused TypeError. |
| 7 | PNPNNPNF | Venmo login spec was never checked. |
| 8 | PFPNNNNP | Only page 0 was read; Cory was omitted. |
| 9 | FNFNNNNF | Unsupported parameter; no phone API spec. |
| 10 | FNPNNPNF | Missing token caused 401; spec unchecked. |
| 11 | FNPNNPNF | Boolean indexing caused TypeError. |
| 12 | FNPNNPNF | Email login failed with invalid credentials. |
| 13 | PPPNNPNP |  |
| 14 | FNPNNFNF | Repeated unchanged login after known 401. |
| 15 | FNPNNPNF | Unsupported show_profile arguments. |
| 16 | PPPNNPNF | Phone API spec was not checked. |
| 17 | PNPNNPNF | Phone login spec was not checked. |
| 18 | PUPNNNNF | Unread contacts may include another Cory. |
| 19 | PPPPNNNF | Commentary included extra code blocks. |
| 20 | PFFFNFNF | Fabricated results and queried Susan's ID. |
| 21 | PUPNNPNP | Unread requests may contain relevant records. |
| 22 | PFFFNFFF | Chose denied request 1915 and fabricated refund. |
| 23 | PFFFNFFF | Used Nancy's 41 as Cory's refund amount. |
| 24 | FNFFNFFF | Called nonexistent API for the wrong request. |
| 25 | PPPNNPNP |  |
| 26 | PPPNNFNP | Repeated identical documentation lookup. |
| 27 | FNFFNPFF | Deletion/add-balance cannot refund Cory. |
| 28 | FNFFNFFF | Approve/deny cannot return Cory's money. |
| 29 | FNFFNPFF | Conflated request ID with transaction ID. |
| 30 | FNFFNPFF | Fabricated a match; Unicode query failed. |
| 31 | PUFFNPFF | Unread pages unknown; fabricated a match. |
| 32 | PFFFNPFF | Irrelevant results were claimed as a match. |
| 33 | PFFFNFFF | Repeated irrelevant query and fabricated match. |
| 34 | PFFFNFFF | Repeated irrelevant query and fabricated match. |
| 35 | PFFFNFFF | Repeated irrelevant query and fabricated match. |
| 36 | PFFFNFFF | Repeated irrelevant query and fabricated match. |
| 37 | PFFFNFFF | Repeated irrelevant query and fabricated match. |
| 38 | PFFFNFNF | Repeated irrelevant query and fabricated match. |

### 76f2c72_1__03

 What is the total cost of my electricity bills for this year? The bills are in "~/bills/" directory of my file system.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | FNNNNNNF | Unauthenticated, undocumented API call failed. |
| 3 | PPNNNFNP | Repeated the same API listing without need. |
| 4 | FPPNNPNF | Login lacked username and required API specs. |
| 5 | PPNNNPNP |  |
| 6 | FNNNNPNF | Called nonexistent API without checking its spec. |
| 7 | PPNNNPNP |  |
| 8 | PPPNNPNF | show_profile spec was not checked before use. |
| 9 | PNPNNPNP |  |
| 10 | PPPNNPNF | show_directory spec was not checked before use. |
| 11 | PPPPNNNP |  |
| 12 | PPUFNNNF | Current year was assumed without date evidence. |
| 13 | PPPNNNNF | show_file spec was not checked before use. |
| 14 | FNNFNNNF | Dollar parsing failed and May's PDF was excluded. |
| 15 | PFPFNPNF | The total omitted the known May PDF bill. |
| 16 | PNUFNNFF | Completion claimed an unverified, incomplete total. |

### 7d7fbf6_1__00

 The "~/photographs/" directory in my file system has photo files organized in sub-directories for each vacation spot. Compress them and save them in "~/photographs/vacations/<vacation_spot>.zip" for each vacation spot, and then delete all vacation spot sub-directories. Here, <vacation_spot> is the name of the vacation spot as it appears in the sub-directory name.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API was called without checking its spec. |
| 2 | PPPNNPNP |  |
| 3 | FNPNNPNF | Call lacked a token and a checked API spec. |
| 4 | FNPNNUNF | Login omitted credentials and a checked spec. |
| 5 | PPPNNPNF | Supervisor API was called without its spec. |
| 6 | PNPNNPNF | Login API spec was not checked. |
| 7 | FNPNNFNF | Repeated query still omitted the access token. |
| 8 | PPPNNPNF | show_directory spec was not checked. |
| 9 | PPPNNNNF | show_directory spec was not checked. |
| 10 | FNFFNNNF | Empty spot name; invalid compression argument. |
| 11 | PPPNNPNP |  |
| 12 | FNFFUPNP | Wrong path; Athens deletion effect is unclear. |
| 13 | FNFFUPNF | Wrong path; Athens deletion effect is unclear. |
| 14 | PPPNNPNF | Extra code block; API spec was not checked. |
| 15 | PPPNNPNF | Read APIs were used without their specs. |
| 16 | PNPFFPNF | Archives were saved outside vacations/. |
| 17 | FNFNNNFF | Wrong location; complete_task was not called. |

### b0a8eae_3__03

 Start playing a playlist on Spotify that has enough songs for my workout today. I do not want to have to change the playlist in the middle of my workout. The workout plan is in Simple Note.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API; no specification checked. |
| 2 | PPNNNPNP |  |
| 3 | FNNNNPNF | Missing token; API specification unchecked. |
| 4 | PPNNNFNP | Repeated the same API listing unnecessarily. |
| 5 | PPPPNPNF | Called APIs without checking full specifications. |
| 6 | FNNNNFNF | Repeated the known token omission. |
| 7 | PPNNNPNF | Search API specification was not checked. |
| 8 | PUUPNNNF | Search coverage unclear; API spec unchecked. |
| 9 | PPFFNNNF | Summed the whole week instead of today. |
| 10 | FNFFNNNP | Used wrong duration and an undefined token. |
| 11 | PPPPNPNF | Supervisor API specification was not checked. |
| 12 | PPNNNPNP |  |
| 13 | PPFFNNNF | Invented a KeyError and equated songs to minutes. |
| 14 | PPFNNPNP | Claims a KeyError that did not occur. |
| 15 | PPPPNPNP |  |
| 16 | PUFFNFNP | Unsupported threshold; broader coverage unclear. |
| 17 | PUFFNFNP | Assumed one song per minute and did not recover. |
| 18 | PUFFNFNP | Repeated the same unsupported threshold. |
| 19 | PUFFNFNP | Repeated the same unsupported threshold. |
| 20 | PUFFNFNP | Repeated the same unsupported threshold. |
| 21 | PUFFNFNP | Repeated the same unsupported threshold. |
| 22 | PUFFNFNP | Repeated the same unsupported threshold. |
| 23 | PUFFNFNP | Repeated the same unsupported threshold. |
| 24 | PUFFNFNP | Repeated the same unsupported threshold. |
| 25 | PUFFNFNP | Chose a playlist without proving sufficient length. |
| 26 | FNPFNNNF | Used a nonexistent API for an unsupported choice. |
| 27 | PPNNNPNP |  |
| 28 | PNPFUPNF | Duration unknown; play_music spec unchecked. |
| 29 | PNPNNNUF | Completion lacks evidence of sufficient duration. |

### b7a9ee9_1__05

 Follow all artists of all classical-genre songs in any of my playlists on Spotify.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords variable caused NameError. |
| 2 | PPPNNPNF | Supervisor API spec was not checked. |
| 3 | PNPNNPNP |  |
| 4 | PPPPNNNP |  |
| 5 | PFFFNNNF | Playlist dict keys were counted as songs. |
| 6 | FNFPNNNP | Strings were treated as song objects. |
| 7 | PPFNNPNP | songs was a list, not a string. |
| 8 | FNFNNPNF | False data claim and nonexistent API. |
| 9 | PPPNNPNP |  |
| 10 | FNPNNPNF | show_song spec was not checked first. |
| 11 | PPPNNPNP |  |
| 12 | FNFNNPNF | A song dict was passed as an integer ID. |
| 13 | PPNNNPNP |  |
| 14 | PPPNNPNP |  |
| 15 | PPPPNPNF | show_playlist spec was never checked. |
| 16 | PPPPNNNP |  |
| 17 | PPPPNNNF | Commentary ended with an unclosed code block. |
| 18 | FNPPNNNF | Missing token caused 401; code fence unclosed. |
| 19 | PPPNNPNP |  |
| 20 | FNPFNPNP | Already-followed artist caused 422. |
| 21 | FUFFNPNF | Wrong field and unpaged following list. |
| 22 | PPPNNPNP |  |
| 23 | FUPFPPNF | Duplicate follow caused partial loop failure. |
| 24 | PPNNNPNP |  |
| 25 | PUFPNPNF | False ID claim; following coverage unclear. |
| 26 | PNPNNNPF | complete_task spec was not checked. |

### cf6abd2_2__01

 Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPFNNNNP | It confuses the checklist item with a note. |
| 2 | PPPNNNNP |  |
| 3 | FNFNNNNF | Search failed; item mistaken for note; no spec. |
| 4 | FNPNNPNF | Login validation failed; spec unchecked. |
| 5 | PPPNNPNF | Supervisor API spec was not checked. |
| 6 | FNPNNPNF | Unknown API failed; spec was not checked. |
| 7 | FNFNNFNF | Repeated guessed API; account claim was false. |
| 8 | PPFNNPNF | Account claim was false; API spec unchecked. |
| 9 | PNPNNPNF | Login API spec was not checked. |
| 10 | PPFNNPNF | Item treated as note; API spec unchecked. |
| 11 | PPFNNPNF | Item treated as note; API spec unchecked. |
| 12 | PPFNNFNF | Item confused; repeated query; spec unchecked. |
| 13 | PPFNNPNF | Item treated as note; API spec unchecked. |
| 14 | PPFNNFNF | Item confused; redundant search; spec unchecked. |
| 15 | PPPNNPNF | Show-note API spec was not checked. |
| 16 | PNPPPNNF | Update API spec was not checked. |
| 17 | PNPNNNPF | Completion API spec was not checked. |

### e7a10f8_1__05

 How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords variable caused NameError. |
| 2 | PPNNNPNF | Supervisor API spec was not checked first. |
| 3 | PPPNNPNP |  |
| 4 | PUNNNNNF | Unread pages may hide longer playlists. |
| 5 | FNFUNNNF | Wrong field caused KeyError; APIs unchecked. |
| 6 | PPPNNPNP |  |
| 7 | PUPUNPNP | Pages and duration units remain unknown. |
| 8 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 9 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 10 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 11 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 12 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 13 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 14 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 15 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 16 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 17 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 18 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 19 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 20 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 21 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 22 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 23 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 24 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 25 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 26 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 27 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 28 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 29 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 30 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 31 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 32 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 33 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 34 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 35 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 36 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 37 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 38 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 39 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 40 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 41 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 42 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 43 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 44 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 45 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 46 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 47 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 48 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 49 | PUUUNFFF | Repeated check; no answer or complete_task. |
| 50 | PUUUNFFF | Repeated check; no answer or complete_task. |

### e7a10f8_2__02

 How long is my shortest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords variable caused NameError. |
| 2 | PPPNNPNF | Supervisor API spec was not checked. |
| 3 | PPPNNPNP |  |
| 4 | PNPNNPNP |  |
| 5 | PPPNNNNP |  |
| 6 | PPPNNNNF | Playlist detail API spec was not checked. |
| 7 | FNFPNNNP | Missing song_ids key caused KeyError. |
| 8 | PPPNNPNP |  |
| 9 | PPUFNPNP | Duration unit was assumed without evidence. |
| 10 | PPUFNFNP | Repeated unsupported millisecond conversion. |
| 11 | PPPNNPNP |  |
| 12 | PPUFNFNP | Repeated unsupported millisecond conversion. |
| 13 | PPUFNPNP | Millisecond unit remained unsupported. |
| 14 | PPUFNFNP | Repeated inspection; unit remained unsupported. |
| 15 | PPUFNFNP | Repeated known value with unsupported unit. |
| 16 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 17 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 18 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 19 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 20 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 21 | PPUFNFNP | Repeated known value with unsupported unit. |
| 22 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 23 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 24 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 25 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 26 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 27 | PPUFNFNP | Repeated known value with unsupported unit. |
| 28 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 29 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 30 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 31 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 32 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 33 | PPUFNFNP | Repeated known value with unsupported unit. |
| 34 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 35 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 36 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 37 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 38 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 39 | PPUFNFNP | Repeated known value with unsupported unit. |
| 40 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 41 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 42 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 43 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 44 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 45 | PPUFNFNP | Repeated known value with unsupported unit. |
| 46 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 47 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 48 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 49 | PPUFNFNP | Repeated conversion using an unsupported unit. |
| 50 | PPUFNFNP | Repeated conversion using an unsupported unit. |

### e7a10f8_3__04

 How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNUFNNNF | Called a nonexistent, undocumented API. |
| 2 | PPPNNPNF | Supervisor API spec was not checked. |
| 3 | PNPNNNNP |  |
| 4 | PUPNNNNF | Pagination was not completed. |
| 5 | PUUFNNNP | Used song count, not total duration. |
| 6 | PNFFNNNP | Used a fabricated 3-minute song average. |
| 7 | PNFFNNFF | Submitted an unsupported estimated duration. |

## development_r2

### 302c169_2__02

 I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unauthorized call; API spec not checked. |
| 2 | FNNNNUNF | Recovery API was guessed and did not exist. |
| 3 | PPPNNPNF | Supervisor API spec was not checked. |
| 4 | FNFNNNNF | Email used for phone-number username field. |
| 5 | PPNNNPNP |  |
| 6 | PNPNNPNP |  |
| 7 | PPNNNNNF | Alarm-list API spec was not checked. |
| 8 | PPPPNNNP |  |
| 9 | PNPPNNNP |  |
| 10 | PNPPPNNF | Update API spec was not checked. |
| 11 | PNPNNNPF | Completion API spec was not checked. |

### 302c169_3__02

 I am going on a vacation. Move my go-to-sleep phone alarm to 20 minutes later and disable the rest.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API called without checking its spec. |
| 2 | PPNNNPNP |  |
| 3 | FNNNNPNF | Alarm read lacked a spec and failed authorization. |
| 4 | PPNNNFNP | Repeated the same API listing without need. |
| 5 | FPNNNPNF | Bad password extraction; required specs unchecked. |
| 6 | FPNNNPNF | Login omitted username; required specs unchecked. |
| 7 | PPNNNPNP |  |
| 8 | PPPNNPNF | Password API spec was not checked. |
| 9 | PPPNNPNF | Alarm API spec was not checked. |
| 10 | PPFFNNNP | Wake Up was baselessly treated as go-to-sleep. |
| 11 | PNFFFNNF | Wrong alarm/time updated; update spec unchecked. |
| 12 | PNFNNNFF | Claimed completion after wrong edits; spec unchecked. |

### 60d0b5b_1__02

 The last Venmo payment request I sent to Robert was an accident and they approved it. Send them the money back.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PFNNNFNP | Repeated API list did not retrieve requests. |
| 3 | PPNNNNNP |  |
| 4 | PFNNNFNP | Repeated API list did not retrieve requests. |
| 5 | PFNNNFNP | Repeated API list did not retrieve requests. |
| 6 | PFNNNFNP | Repeated API list did not retrieve requests. |
| 7 | FNNNNNNP | Undefined access-token variable caused NameError. |
| 8 | PPNNNPNP |  |
| 9 | FNNNNPNF | Password parsing failed; API spec was unchecked. |
| 10 | PPPNNPNF | Supervisor password API spec was never checked. |
| 11 | PPPNNPNP |  |
| 12 | PPPNNPNP |  |
| 13 | PUFFNNNF | Picked the oldest shown item; more pages unchecked. |
| 14 | PPFNNFNF | Wrong ID claim; repeated query and extra code blocks. |
| 15 | PPNNNNNP |  |
| 16 | PPPNNFNP | Repeated the API list without new information. |
| 17 | FNFFNNNP | Delete is not a refund; completed request was rejected. |
| 18 | PNFFNFFF | Gave up despite create_transaction; completion spec absent. |

### 60d0b5b_2__03

 The last Venmo payment request I sent to Cory was an accident and they approved it. Send them the money back.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PNNNNNNP |  |
| 2 | PNNNNNNP |  |
| 3 | FNNNNNNP | Undefined access-token variable caused failure. |
| 4 | FNNNNPNF | Passwords was undefined; login spec unchecked. |
| 5 | PPNNNPNF | Credential API spec was not checked. |
| 6 | FNPNNPNF | Boolean list was indexed; login spec unchecked. |
| 7 | PNPNNPNF | Venmo login spec was not checked. |
| 8 | PPPNNNNP |  |
| 9 | FFFFNNNF | Cory claim skipped pages; phone API was guessed. |
| 10 | FNPNNPNF | Token was missing; phone API spec unchecked. |
| 11 | FNPNNPNF | Boolean list was indexed; login spec unchecked. |
| 12 | FNPNNPNF | Login failed; phone login spec was unchecked. |
| 13 | PPPNNPNP |  |
| 14 | FNPNNFNF | Repeated unchanged invalid login without its spec. |
| 15 | FNPNNPNF | Profile call used unsupported, undocumented args. |
| 16 | PPPNNPNF | Phone profile spec was not checked. |
| 17 | PNPNNPNF | Phone login spec was not checked. |
| 18 | PPPNNPNF | Contact-search spec was not checked. |
| 19 | PPPPNNNF | Extra executable blocks appeared in commentary. |
| 20 | PFFFNFNF | Fabricated searches; queried a known non-Cory ID. |
| 21 | PPPPNPNP |  |
| 22 | PFFFNFFF | Used a denied request and invented refund success. |
| 23 | PFFFNFFF | Treated Nancy's $41 request as Cory's. |
| 24 | FNFFNFFF | Nonexistent API, wrong request, and fake success. |
| 25 | PNPNNPNP |  |
| 26 | PNPNNFNP | Repeated the same docs query without new need. |
| 27 | FNFFNFFF | Deletion failed; the plan would not repay Cory. |
| 28 | FNFFNFFF | Unauthorized approve would not repay Cory. |
| 29 | FNFFNFFF | Assumed an ID mapping and fabricated an update. |
| 30 | FNFFNPFF | Encoding failed; transaction and success invented. |
| 31 | PFFFNPFF | Results were unrelated; update success invented. |
| 32 | PFFFNPFF | ID search missed the target; result was invented. |
| 33 | PFFFNFFF | Repeated the same failed search and fake result. |
| 34 | PFFFNFFF | Repeated the same failed search and fake result. |
| 35 | PFFFNFFF | Repeated the same failed search and fake result. |
| 36 | PFFFNFFF | Repeated the same failed search and fake result. |
| 37 | PFFFNFFF | Repeated the same failed search and fake result. |
| 38 | PFFFNFNF | Repeated the same failed search and fake result. |

### 76f2c72_1__03

 What is the total cost of my electricity bills for this year? The bills are in "~/bills/" directory of my file system.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | FNNNNNNF | Undocumented call failed authentication. |
| 3 | PPNNNFNP | Repeated the same API listing without need. |
| 4 | FPPNNPNF | Undocumented login omitted a required field. |
| 5 | PPNNNPNP |  |
| 6 | FNNNNPNF | Undocumented, nonexistent API call failed. |
| 7 | PPNNNPNP |  |
| 8 | PPPNNPNF | show_profile was called without its spec. |
| 9 | PNPNNPNP |  |
| 10 | PPPNNPNF | show_directory was called without its spec. |
| 11 | PPPPNNNP |  |
| 12 | PPUFNNNF | 2023 was assumed without checking current date. |
| 13 | PPPNNNNF | show_file was called without its spec. |
| 14 | FPPPNPNF | Parsing failed; show_file spec was not checked. |
| 15 | PFUFNPNF | May's PDF was omitted from the computed total. |
| 16 | PFUFNNUF | Submitted an unverified subtotal; API spec unchecked. |

### 7d7fbf6_1__00

 The "~/photographs/" directory in my file system has photo files organized in sub-directories for each vacation spot. Compress them and save them in "~/photographs/vacations/<vacation_spot>.zip" for each vacation spot, and then delete all vacation spot sub-directories. Here, <vacation_spot> is the name of the vacation spot as it appears in the sub-directory name.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API; specification not checked. |
| 2 | PPPNNPNP |  |
| 3 | FNPNNPNF | Missing token; specification not checked. |
| 4 | FNPNNPNF | Missing login fields; spec not checked. |
| 5 | PPPNNPNF | Supervisor API specification not checked. |
| 6 | PNPNNPNF | Login specification not checked. |
| 7 | FNPNNFNF | Token omitted again; spec not checked. |
| 8 | PPPNNPNF | Directory API specification not checked. |
| 9 | PPPNNNNF | Directory API specification not checked. |
| 10 | FNFFNNNF | Empty spot name; unsupported parameter. |
| 11 | PPPNNPNP |  |
| 12 | FNFFNPNP | Empty spot name and wrong archive path. |
| 13 | FNFFUPNF | Empty archive name; partial effect unresolved. |
| 14 | PPPNNPNF | Extra code block; API spec not checked. |
| 15 | PPPNNPNF | Directory APIs used without specifications. |
| 16 | PNFFFPNF | Archives written outside required directory. |
| 17 | FNFNNNFF | False completion; complete_task not called. |

### b0a8eae_3__03

 Start playing a playlist on Spotify that has enough songs for my workout today. I do not want to have to change the playlist in the middle of my workout. The workout plan is in Simple Note.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Called a nonexistent, undocumented API. |
| 2 | PPNNNPNP |  |
| 3 | FNNNNNNF | Missing token caused 401; API undocumented. |
| 4 | PPNNNFNP | Repeated the same API list without need. |
| 5 | PPPNNPNF | Called APIs without checking their specs. |
| 6 | FNPNNFNF | Omitted the token again; API undocumented. |
| 7 | PPPNNPNF | Called search_notes without its full spec. |
| 8 | PPUPNNNF | Exact title unverified; API undocumented. |
| 9 | PPPFNNNP | Summed the full week instead of today. |
| 10 | FNPNNNNP | spotify_access_token was undefined. |
| 11 | PPPNNPNF | Supervisor API spec was not checked. |
| 12 | PPPNNPNP |  |
| 13 | PPFFNNNF | Invented KeyError; equated minutes to songs. |
| 14 | PPNNNNNP |  |
| 15 | PPPFNFNP | Summed all playlists, not each playlist. |
| 16 | PPPFNFNP | Reused the invalid 315-song threshold. |
| 17 | PNFFNFNP | Unsupported 315-song claim repeated. |
| 18 | PPFFNFNP | Repeated search; None was called an error. |
| 19 | PPFFNFNP | Repeated search; None was called an error. |
| 20 | PPFFNFNP | Repeated search; None was called an error. |
| 21 | PPFFNFNP | Repeated search; None was called an error. |
| 22 | PPFFNFNP | Repeated search; None was called an error. |
| 23 | PPFFNFNP | Repeated search; None was called an error. |
| 24 | PPFFNFNP | Repeated search; None was called an error. |
| 25 | PPPFNFNP | Chose a playlist below its own threshold. |
| 26 | FNPFNNNF | Nonexistent API; chosen list was too short. |
| 27 | PPNNNPNP |  |
| 28 | PNPFUPNF | Sufficiency unverified; API spec unchecked. |
| 29 | PNPNNNUF | Completed with sufficiency unverified. |

### b7a9ee9_1__05

 Follow all artists of all classical-genre songs in any of my playlists on Spotify.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords variable caused NameError. |
| 2 | PPNNNPNF | Supervisor password API spec was not checked. |
| 3 | PPPNNPNP |  |
| 4 | PPPNNNNP |  |
| 5 | PFFNNNNF | Playlist objects were mistaken for songs. |
| 6 | FNFNNNNP | Strings were treated as song objects. |
| 7 | PPFNNPNP | Claimed a string, but songs was a list. |
| 8 | FNFNNPNF | Used a nonexistent API and misread song entries. |
| 9 | PPNNNPNP |  |
| 10 | FNFNNPNF | Undocumented call used a dict as song_id. |
| 11 | PPNNNPNP |  |
| 12 | FNFNNPNF | A song dict was passed instead of an integer. |
| 13 | PPFNNPNP | Called song_id a string; it was a dict. |
| 14 | PPPNNPNP |  |
| 15 | PPPNNPNF | show_playlist spec was never checked. |
| 16 | PPPPNNNP |  |
| 17 | PPPPNNNP |  |
| 18 | FNPFNNNF | Missing token and duplicate artist targets. |
| 19 | PPNNNPNP |  |
| 20 | FNPFNPNP | Blind follow hit an already-followed artist. |
| 21 | FPFNNPNF | Wrong ID key; API spec was not checked. |
| 22 | PPPNNPNP |  |
| 23 | FUFFPPNF | Stale, possibly partial state caused refollow. |
| 24 | PPFNNPNP | The artist IDs visibly matched the target IDs. |
| 25 | PPPPNPNF | Following-artists API spec was not checked. |
| 26 | PNPNNNPF | complete_task spec was not checked. |

### cf6abd2_2__01

 Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPPNNNNP |  |
| 3 | FNNNNNNF | Unauthorized call; API spec was not checked. |
| 4 | FNNNNPNF | Login omitted required credentials. |
| 5 | PPNNNPNF | API specification was not checked. |
| 6 | FNPNNPNF | Called a nonexistent, undocumented API. |
| 7 | FNPNNPNF | Called a nonexistent, undocumented API. |
| 8 | PPPNNPNF | API specification was not checked. |
| 9 | PNPNNPNF | API specification was not checked. |
| 10 | PPPNNNNF | API specification was not checked. |
| 11 | PPFNNPNF | Confused the checklist item with a note. |
| 12 | PPFNNFNF | Repeated query and confused item with note. |
| 13 | PPFNNPNF | Confused the checklist item with a note. |
| 14 | PPFNNPNF | Confused the checklist item with a note. |
| 15 | PPPNNNNF | API specification was not checked. |
| 16 | PNPPPNNF | API specification was not checked. |
| 17 | PNPNNNPF | complete_task specification was not checked. |

### e7a10f8_1__05

 How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined variable caused NameError. |
| 2 | PPNNNPNF | Supervisor API lacked prior documentation. |
| 3 | PPPNNPNP |  |
| 4 | PPNNNNNP |  |
| 5 | FPFFNNNF | Undocumented API and field led to KeyError. |
| 6 | PPPNNPNP |  |
| 7 | PUPUNPNP | Pagination and duration unit remain unverified. |
| 8 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 9 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 10 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 11 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 12 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 13 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 14 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 15 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 16 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 17 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 18 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 19 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 20 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 21 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 22 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 23 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 24 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 25 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 26 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 27 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 28 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 29 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 30 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 31 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 32 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 33 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 34 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 35 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 36 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 37 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 38 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 39 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 40 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 41 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 42 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 43 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 44 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 45 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 46 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 47 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 48 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 49 | PNUNNFNP | Result remained unshown; operation was repeated. |
| 50 | PNUNNFFP | Result unshown; repeated, with no complete_task call. |

### e7a10f8_2__02

 How long is my shortest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords caused NameError. |
| 2 | PPNNNPNF | Supervisor API specification was not checked. |
| 3 | PPPNNPNP |  |
| 4 | PNPNNPNP |  |
| 5 | PPPNNNNP |  |
| 6 | PPPNNNNF | show_playlist specification was not checked. |
| 7 | FNFPNNNP | KeyError; playlist fields were confused. |
| 8 | PPPNNPNP |  |
| 9 | PNUFNPNP | Duration unit was assumed without evidence. |
| 10 | PNUFNFNP | Repeated the same unsupported conversion. |
| 11 | PPPNNPNP |  |
| 12 | PNUFNFNP | Repeated the same unsupported conversion. |
| 13 | PPPPNPNP |  |
| 14 | PPUFNFNP | Repeated known data; unit remained unsupported. |
| 15 | PPUNNFNP | Re-read known value; unit claim unsupported. |
| 16 | PNUFNFNP | Unsupported conversion did not resolve the error. |
| 17 | PNUFNFNP | Unsupported conversion did not resolve the error. |
| 18 | PNUFNFNP | Unsupported conversion did not resolve the error. |
| 19 | PNUFNFNP | Unsupported conversion did not resolve the error. |
| 20 | PNUFNFNP | Unsupported conversion did not resolve the error. |
| 21 | PPUNNFNP | Repeated known value; unit claim unsupported. |
| 22 | PNUFNFNP | Repeated an unsupported conversion. |
| 23 | PNUFNFNP | Repeated an unsupported conversion. |
| 24 | PNUFNFNP | Repeated an unsupported conversion. |
| 25 | PNUFNFNP | Repeated an unsupported conversion. |
| 26 | PNUFNFNP | Repeated an unsupported conversion. |
| 27 | PPUNNFNP | Repeated known value; unit claim unsupported. |
| 28 | PNUFNFNP | Repeated an unsupported conversion. |
| 29 | PNUFNFNP | Repeated an unsupported conversion. |
| 30 | PNUFNFNP | Repeated an unsupported conversion. |
| 31 | PNUFNFNP | Repeated an unsupported conversion. |
| 32 | PNUFNFNP | Repeated an unsupported conversion. |
| 33 | PPUNNFNP | Repeated known value; unit claim unsupported. |
| 34 | PNUFNFNP | Repeated an unsupported conversion. |
| 35 | PNUFNFNP | Repeated an unsupported conversion. |
| 36 | PNUFNFNP | Repeated an unsupported conversion. |
| 37 | PNUFNFNP | Repeated an unsupported conversion. |
| 38 | PNUFNFNP | Repeated an unsupported conversion. |
| 39 | PPUNNFNP | Repeated known value; unit claim unsupported. |
| 40 | PNUFNFNP | Repeated an unsupported conversion. |
| 41 | PNUFNFNP | Repeated an unsupported conversion. |
| 42 | PNUFNFNP | Repeated an unsupported conversion. |
| 43 | PNUFNFNP | Repeated an unsupported conversion. |
| 44 | PNUFNFNP | Repeated an unsupported conversion. |
| 45 | PPUNNFNP | Repeated known value; unit claim unsupported. |
| 46 | PNUFNFNP | Repeated an unsupported conversion. |
| 47 | PNUFNFNP | Repeated an unsupported conversion. |
| 48 | PNUFNFNP | Repeated an unsupported conversion. |
| 49 | PNUFNFNP | Repeated an unsupported conversion. |
| 50 | PNUFNFNP | Repeated an unsupported conversion. |

### e7a10f8_3__04

 How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNFNNNF | Unknown API; guessed duration rule. |
| 2 | PPPNNPNF | Supervisor API spec was not checked. |
| 3 | PNPNNNNP |  |
| 4 | PPPNNNNF | Pagination loop required but not performed. |
| 5 | PUUFNNNP | Coverage unknown; song count is not duration. |
| 6 | PNFFNNNP | Duration was based on an invented average. |
| 7 | PNUFNNFF | Estimated duration submitted without API spec. |

## development_format

### 60d0b5b_2__03

 The last Venmo payment request I sent to Cory was an accident and they approved it. Send them the money back.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPNNNNNP |  |
| 3 | FNNNNNNP | Undefined token caused NameError. |
| 4 | FNNNNPNF | Undefined passwords caused NameError. |
| 5 | PPNNNPNF | Supervisor API spec was not checked. |
| 6 | FNPNNPNF | Bad filter caused a TypeError. |
| 7 | PNPNNPNF | Venmo login spec was not checked. |
| 8 | PFPNNNNP | Only the first request page was read. |
| 9 | FNFNNNNF | False no-Cory claim; undocumented arg. |
| 10 | FNPNNPNF | Phone API lacked a token and prior spec. |
| 11 | FNPNNPNF | Bad filter caused TypeError; no API spec. |
| 12 | FNPNNPNF | Login failed; phone login spec was unchecked. |
| 13 | PPPNNPNP |  |
| 14 | FNPNNFNF | Repeated the same known-invalid login. |
| 15 | FNPNNPNF | Undocumented profile call used invalid args. |
| 16 | PPPNNPNF | Phone profile spec was not checked. |
| 17 | PNPNNPNF | Phone login spec was not checked. |
| 18 | PUPNNPNF | Pagination was unclear; API spec unchecked. |
| 19 | PUPUNNNF | Cory uniqueness unclear; extra code blocks. |
| 20 | PFFNNNNF | Fabricated searches; queried wrong ID. |
| 21 | PFFNNPNP | False prior result; omitted later pages. |
| 22 | PFFFNNFF | Invented refund; selected a denied request. |
| 23 | PFFFNFFF | Used Nancy's amount and invented a refund. |
| 24 | FNFFNFFF | Called nonexistent API for the wrong request. |
| 25 | PPPNNPNP |  |
| 26 | PPPNNFNP | Repeated the same API discovery needlessly. |
| 27 | FNFFNPFF | Deletion failed; fabricated a wrong refund. |
| 28 | FNFFNFFF | Ignored completed status and invented success. |
| 29 | FNFFNFFF | Assumed request ID was a transaction ID. |
| 30 | FNFFNPFF | Fabricated transaction; query encoding failed. |
| 31 | PFFFNPFF | Results were unrelated; success was fabricated. |
| 32 | PFFFNPFF | Unrelated ID results; fabricated success. |
| 33 | PFFFNFFF | Repeated the same failed search and fiction. |
| 34 | PFFFNFFF | Repeated the same failed search and fiction. |
| 35 | PFFFNFFF | Repeated the same failed search and fiction. |
| 36 | PFFFNFFF | Repeated the same failed search and fiction. |
| 37 | PFFFNFFF | Repeated the same failed search and fiction. |
| 38 | PFFFNFNF | Repeated failed search; fabricated target data. |

### b0a8eae_3__03

 Start playing a playlist on Spotify that has enough songs for my workout today. I do not want to have to change the playlist in the middle of my workout. The workout plan is in Simple Note.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNFFNNNF | Guessed title; nonexistent undocumented API. |
| 2 | PPNNNNNP |  |
| 3 | FNNNNNNF | Missing token; API spec was not checked. |
| 4 | PPNNNFNP | Repeated an already-known API listing. |
| 5 | PPPNNPNF | API specs were not checked before login. |
| 6 | FNNNNFNF | Retried without the known access token. |
| 7 | PPNNNPNF | search_notes spec was not checked. |
| 8 | PPUNNNNF | Exact-title coverage unclear; API undocumented. |
| 9 | PPPFNNNP | Summed the whole week instead of today. |
| 10 | FNFFNNNP | Undefined token and wrong 315-minute premise. |
| 11 | PPPNNPNF | Supervisor password API spec was not checked. |
| 12 | PPNNNPNP |  |
| 13 | PPFFNNNF | Invented an error and equated minutes to songs. |
| 14 | PPFNNPNP | Treated a normal None result as a missing field. |
| 15 | PPPFNPNP | Computed a combined total, not per-playlist totals. |
| 16 | PPFFNNNP | Used 315 songs for a single day's workout. |
| 17 | PNFFNFNP | Unsupported 315-song requirement; no recovery. |
| 18 | PPFFNFNP | Repeated the same invalid threshold query. |
| 19 | PPFFNFNP | Repeated the same invalid threshold query. |
| 20 | PPFFNFNP | Repeated the same invalid threshold query. |
| 21 | PPFFNFNP | Repeated the same invalid threshold query. |
| 22 | PPFFNFNP | Repeated the same invalid threshold query. |
| 23 | PPFFNFNP | Repeated the same invalid threshold query. |
| 24 | PPFFNFNP | Repeated the same invalid threshold query. |
| 25 | PPFFNFNP | Chose a playlist known not to meet its threshold. |
| 26 | FNPFNNNF | Called an undocumented nonexistent API. |
| 27 | PPNNNPNP |  |
| 28 | PNPFUPNF | Playlist sufficiency is unknown; API undocumented. |
| 29 | PNPNNNUF | Completed with playlist sufficiency unverified. |

### b7a9ee9_1__05

 Follow all artists of all classical-genre songs in any of my playlists on Spotify.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords caused NameError. |
| 2 | PPNNNPNF | Supervisor API spec was not checked. |
| 3 | PPPNNPNP |  |
| 4 | PPPNNNNP |  |
| 5 | PPFNNNNF | Playlist dict keys were treated as songs. |
| 6 | FNFPNNNP | String entries caused AttributeError. |
| 7 | PPFNNPNP | It misidentified a list as a string. |
| 8 | FNFNNPNF | It invented get_song and misread song entries. |
| 9 | PPNNNPNP |  |
| 10 | FNNNNPNF | show_song received an unsupported token. |
| 11 | PPPNNPNP |  |
| 12 | FNFNNPNF | A song object was passed as the integer ID. |
| 13 | PPFNNPNP | It claimed the song object was a string. |
| 14 | PPPNNPNP |  |
| 15 | PPPNNPNF | show_playlist spec was never checked. |
| 16 | PPPPNNNP |  |
| 17 | PPPNNNNF | Commentary ended with an unclosed code fence. |
| 18 | FNFFNNNF | No token was sent; artist list had duplicates. |
| 19 | PPPNNPNP |  |
| 20 | FNPFNPNP | The loop hit an already-followed artist. |
| 21 | FPFPNPNF | It used id instead of artist_id. |
| 22 | PPPNNPNP |  |
| 23 | FPPFPPNF | Duplicate targets caused failure after writes. |
| 24 | PPFNNPNP | It falsely claimed matching IDs mismatched. |
| 25 | PPFPNPNF | Its ID-mismatch claim contradicted the data. |
| 26 | PNPNNNPF | complete_task spec was never checked. |

### e7a10f8_1__05

 How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords caused NameError. |
| 2 | PPNNNPNF | Recovered variable, but API spec was not checked. |
| 3 | PPPNNNNP |  |
| 4 | PUNNNNNF | Page completeness unknown; pagination omitted. |
| 5 | FNFFNNNF | KeyError; guessed field/unit without API docs. |
| 6 | PPPNNPNP |  |
| 7 | PUUFNPNP | Pagination and duration unit are unverified. |
| 8 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 9 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 10 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 11 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 12 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 13 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 14 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 15 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 16 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 17 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 18 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 19 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 20 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 21 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 22 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 23 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 24 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 25 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 26 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 27 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 28 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 29 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 30 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 31 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 32 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 33 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 34 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 35 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 36 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 37 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 38 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 39 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 40 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 41 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 42 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 43 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 44 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 45 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 46 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 47 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 48 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 49 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |
| 50 | PUUFNFFP | Coverage/unit unknown; repeated without complete_task. |

## holdout_format

### 07b42fd_1__05

 Follow all the classical artists on Spotify that have at least 22 followers.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPPNNNNF | Password API spec was not checked. |
| 2 | FNNNNNNF | Unexpected access_token argument caused failure. |
| 3 | FNNNNPNF | Nonexistent show_artists API caused failure. |
| 4 | FNNNNPNF | page_limit 100 exceeded the API maximum. |
| 5 | PPPNNPNF | search_artists spec was not checked. |
| 6 | FPFPNPNF | Wrong artist ID key caused KeyError. |
| 7 | PPPNNPNP |  |
| 8 | PNPPPPPF | API specs were not checked before calls. |

### 07b42fd_2__01

 Follow all the edm artists on Spotify that have at least 23 followers.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPPNNNNF | Supervisor API spec was not checked. |
| 3 | FNNNNNNF | Unsupported access_token caused failure. |
| 4 | FNFNNPNF | Used a nonexistent, undocumented API. |
| 5 | PPNNNPNF | Search API specification was not checked. |
| 6 | FNFNNFNF | List response was parsed as a dictionary. |
| 7 | PNPNNPNP |  |
| 8 | FNFFNNNF | Wrong field; EDM scope was unsupported. |
| 9 | PPPNNPNP |  |
| 10 | FUFFNPNF | Wrong ID and incomplete source scope. |
| 11 | PPPNNFNP | Repeated an already retrieved API spec. |
| 12 | PUUFUPNF | Genre and full-page scope were unverified. |
| 13 | PNFNNNFF | Completion followed an incomplete search. |

### 07b42fd_3__00

 Follow all the reggae artists on Spotify that have at least 21 followers.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPPNNNNF | Password API spec was not checked. |
| 2 | FNNNNNNF | Unknown API caused execution failure. |
| 3 | PPNNNPNP |  |
| 4 | FNNNNPNF | Bad parameter caused execution failure. |
| 5 | PUPNNPNF | Unread pages may contain relevant artists. |
| 6 | FUPPNNNF | Auth failed; artist coverage remains unknown. |
| 7 | PUPPPPNF | Artist coverage remains unknown. |
| 8 | PNNNNNUF | Completion lacks evidence of all artists. |

### 229360a_2__00

 I need to cleanup my Spotify libraries. Keep only those songs and albums in my song and album library, respectively, that I have liked and downloaded, and remove the rest. An album is downloaded if all songs in it are downloaded. Keep my playlist library as is for now.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPPNNNNF | Supervisor API used without prior spec. |
| 2 | PUNNNNNF | Unread pages may contain library items. |
| 3 | FNFFNNNF | KeyError, wrong album rule, extra code block. |
| 4 | PPPNNPNP |  |
| 5 | PPPNNPNP |  |
| 6 | PFPNNFNP | Repeated irrelevant playlist-doc lookup. |
| 7 | FNPNNPNP | Guessed API name returned 422. |
| 8 | FNPNNPNP | Guessed API name returned 422. |
| 9 | PNFFNFPF | Failed task on incomplete API discovery. |

### 22cc237_1__02

 I went on a dinner with some of my coworkers yesterday. I paid the entire bill to simplify the payment. I've made a note of individual shares in simple note. Some people have already sent me their share on venmo. Make payment requests for others with a description note "Work Dinner".

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API failed; spec was not checked. |
| 2 | PPPNNPNP |  |
| 3 | FNNNNPNF | Unauthorized call; spec was not checked. |
| 4 | PPPNNFNP | Repeated an already-seen API listing. |
| 5 | PPPNNPNP |  |
| 6 | FNNNNPNF | Unknown Supervisor API; spec not checked. |
| 7 | PPPNNPNP |  |
| 8 | PPPNNPNF | show_profile called without its API spec. |
| 9 | PPPNNPNF | Extra unexecuted code block broke protocol. |
| 10 | FNFNNNFF | Fabricated password; no code or completion. |

### 27e1026_2__05

 What is the title of the newest released song in my Spotify account from across my song, album and playlist libraries?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPPNNNNF | Supervisor API spec was not checked. |
| 2 | PPFFNNNP | Song details were fabricated. |
| 3 | PPNNNPNP |  |
| 4 | PPNNNNNP |  |
| 5 | FNFFNNNP | Used unsupported release-date sorting. |
| 6 | FNNFNPNP | Page limit violated the documented cap. |
| 7 | PFFFNPNP | Only one global page was checked. |
| 8 | PNFFNNFF | Answer lacks library-wide evidence. |

### 287e338_1__01

 Name the artist most recommended to me on Spotify.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPPNNNNF | Password API spec was not checked. |
| 2 | PNPNNNNP |  |
| 3 | PPPNNNNP |  |
| 4 | PPNNNNNP |  |
| 5 | PUUNNNNF | Only page 0 fetched; completeness unknown. |
| 6 | PUUFNNNP | Unread pages may change the top artist. |
| 7 | PUUFNNUF | Answer relies on unread pages; spec unchecked. |

### 29caf6f_3__02

 Leslie has asked for my movie recommendations via phone text message. Reply to them with a list of comma-separated movie titles from my Simple Note account as per their request.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API; specification was not checked. |
| 2 | PPNNNPNP |  |
| 3 | FNNNNPNF | Unauthorized call lacked the required API spec. |
| 4 | PPNNNFNP | Repeated API listing added no new information. |
| 5 | FNFNNFNF | Invented credential caused authentication failure. |
| 6 | FNNNNFNP | Undefined variable caused the recovery to fail. |
| 7 | PPNNNPNF | Supervisor API specification was not checked. |
| 8 | FNUNNPNF | Auth combination failed; login spec was unchecked. |
| 9 | FNNNNFNF | Invalid parameter and known auth issue were ignored. |
| 10 | PPNNNPNP |  |
| 11 | FNNNNFNF | Repeated unauthorized call; contact spec unchecked. |
| 12 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 13 | FNNNNFNP | Repeated call omitted the required access token. |
| 14 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 15 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 16 | FPNNNFNF | Password parsing failed; supervisor spec unchecked. |
| 17 | PPPNNPNF | Supervisor API specification was not checked. |
| 18 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 19 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 20 | FNNNNFNP | Repeated call omitted the required access token. |
| 21 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 22 | PPPNNFNF | Credential lookup was redundant and undocumented. |
| 23 | FNNNNFNP | Repeated call omitted the required access token. |
| 24 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 25 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 26 | FNNNNFNP | Repeated call omitted the required access token. |
| 27 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 28 | FNNNNFNP | Repeated call omitted the required access token. |
| 29 | FNUNNFNF | Repeated known-invalid login; spec unchecked. |
| 30 | FNNNNFNP | Repeated call omitted the required access token. |
| 31 | FNNNNFNP | Repeated call omitted the required access token. |
| 32 | FNNNNFNP | Repeated call omitted the required access token. |
| 33 | FNNNNFNP | Repeated call omitted the required access token. |
| 34 | FNNNNFNP | Repeated call omitted the required access token. |
| 35 | FNNNNFNP | Repeated call omitted the required access token. |
| 36 | FNNNNFNP | Repeated call omitted the required access token. |
| 37 | FNNNNFNP | Repeated call omitted the required access token. |
| 38 | FNNNNFNP | Repeated call omitted the required access token. |
| 39 | FNNNNFNP | Repeated call omitted the required access token. |
| 40 | FNNNNFNP | Repeated call omitted the required access token. |
| 41 | FNNNNFNP | Repeated call omitted the required access token. |
| 42 | FNNNNFNP | Repeated call omitted the required access token. |
| 43 | FNNNNFNP | Repeated call omitted the required access token. |
| 44 | FNNNNFNP | Repeated call omitted the required access token. |
| 45 | FNNNNFNP | Repeated call omitted the required access token. |
| 46 | FNNNNFNP | Repeated call omitted the required access token. |
| 47 | FNNNNFNP | Repeated call omitted the required access token. |
| 48 | FNNNNFNP | Repeated call omitted the required access token. |
| 49 | FNNNNFNP | Repeated call omitted the required access token. |
| 50 | FNNNNFFP | Repeated unauthorized call; task ended undelivered. |

### 2a163ab_3__04

 Like all the venmo transactions from yesterday or today involving any of my coworkers on my venmo social feed.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PNNNNNNP |  |
| 2 | PNNNNNNP |  |
| 3 | PNNNNNNP |  |
| 4 | PPNNNNNF | API spec unchecked before password call. |
| 5 | FNNNNNNP | Boolean indexing caused a TypeError. |
| 6 | PNPNNPNP |  |
| 7 | PNNNNNNP |  |
| 8 | PNNNNNNP |  |
| 9 | PNNNNNNP |  |
| 10 | FNNNNNNP | Undefined token caused a NameError. |
| 11 | FNFNNPNP | Venmo token was invalid for the phone API. |
| 12 | PNPNNPNP |  |
| 13 | PNNNNFNP | Repeated an already-known API listing. |
| 14 | PPNNNFNF | Repeated password read; API spec unchecked. |
| 15 | PNPNNPNP |  |
| 16 | PFPNNPNF | Own-number query did not prove all coworkers. |
| 17 | FNNNNNNF | Undefined token; extra commentary code block. |
| 18 | PPPNNPNF | Paginated searches did not process all pages. |
| 19 | PNNNNNNF | Extra code block appeared in commentary. |
| 20 | PUNNNNNF | Ten-page cap left feed coverage unknown. |
| 21 | PFNFFNNF | Liked coworker transactions on four dates. |
| 22 | PNUNNNFF | Completed despite likes spanning four dates. |

### 34d9492_2__03

 Arrange my "~/photographs/vacations/" directory by organizing the photos from three vacations. The files created in March and April of this year correspond to Rome and Santorini, respectively, while the others are from Berlin. Move them into sub-directories named after their respective vacation spots, maintaining the original file names.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API called without its spec. |
| 2 | PPPNNPNP |  |
| 3 | FNPNNPNF | Wrong argument; full API spec was not checked. |
| 4 | FNPNNPNF | Call lacked auth and full API spec. |
| 5 | PPPNNFNP | Repeated API list despite login already known. |
| 6 | FNFFNFNF | Guessed credentials; login failed. |
| 7 | PPPNNPNF | Supervisor API spec was not checked. |
| 8 | PNPNNPNF | Login API spec was not checked. |
| 9 | PPPNNPNF | Directory API spec was not checked. |
| 10 | PPPNNNNF | Extra code block and no API specs. |

### 3c13f5a_1__02

 I paid for our last month's electricity bill. Its amount is supposed to be shared equally among my roommates and me. Make venmo requests to my roommates, with a description note, "For electricity bill.". The bill receipt is in my file system.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API used before its spec was checked. |
| 2 | PPNNNPNP |  |
| 3 | PPNNNPNP |  |
| 4 | FNNNNNNF | Required access token was omitted. |
| 5 | PPNNNFNP | Repeated the same API listing without need. |
| 6 | FNFNNFNF | Invented credentials caused login failure. |
| 7 | PPNNNPNF | Supervisor API spec was not checked. |
| 8 | FNPNNPNF | Password extraction raised TypeError. |
| 9 | FNFNNPNF | Prior TypeError was miscalled a syntax error. |
| 10 | PPNNNFNP | Repeated a known password without new evidence. |
| 11 | FNPNNFNF | Repeated credentials already known to fail. |
| 12 | PNNNNPNF | Phone login spec was never checked. |
| 13 | PUPNNNNF | Contact pagination was not exhausted. |
| 14 | FNFNNNNF | Guessed file and API were unsupported. |
| 15 | PPNNNPNP |  |
| 16 | FNPNNPNF | Wrong argument used without checking the spec. |
| 17 | FNFNNPNF | A placeholder path was invented. |
| 18 | PNNNNPNF | File-system login spec was not checked. |
| 19 | FNFNNPNF | The invented path was reused. |
| 20 | FNNNNFNF | Known token requirement was ignored. |
| 21 | PPPNNPNF | show_directory spec was not checked. |
| 22 | PPPNNPNF | show_directory spec was not checked. |
| 23 | PPUUNPNF | Current date was never obtained for last month. |
| 24 | PNPPNNNF | Commentary contained extra code blocks. |
| 25 | PNPFNNNF | Proposed sending money instead of requesting it. |
| 26 | PNFNNNFF | No requests ran, yet completion was claimed. |

### 692c77d_3__00

 Give a 4-star rating to all songs in my Spotify album library which I have liked. If I have already rated it lower, increase it to 4.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPPNNNNF | Supervisor API specification was not checked. |
| 2 | PFNFNNNP | Playlists cannot establish album-library scope. |
| 3 | FFFFNNNF | Playlist songs were assumed liked; API missing. |
| 4 | PPNNNPNP |  |
| 5 | FFFFNPNF | Used aggregate rating and an invalid argument. |
| 6 | PPNNNPNP |  |
| 7 | FFFFNPNF | Wrong rating scope; update arguments invalid. |
| 8 | PPNNNPNP |  |
| 9 | FFFFNPNF | Review query and ownership handling were wrong. |
| 10 | PPNNNPNP |  |
| 11 | FFFFUPNF | It attempted to update another user's review. |
| 12 | PFFFUPNF | Album scope, pagination, and unrated songs omitted. |
| 13 | FNFNNNFF | No complete_task call; success claim unsupported. |

### 6ea6792_3__02

 Accept all pending Venmo payment requests from my coworkers and friends.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | FNNNNNNF | Missing token; API spec was not checked. |
| 3 | FNFNNPNF | Fabricated password caused invalid credentials. |
| 4 | PPPNNPNF | Supervisor API spec was not checked. |
| 5 | PNPNNPNF | Login API spec was not checked. |
| 6 | FNNNNFNF | Repeated request without the access token. |
| 7 | PNNNNFNF | Relogin ignored that no token was sent. |
| 8 | PPFNNPNF | Approved items were mislabeled as pending. |
| 9 | PFUFUNNF | No contact check; requester status unknown. |
| 10 | FFUNNNFF | No contact evidence or complete_task call. |

### 771d8fc_3__02

 All phone text messages and voice messages from 5708520672 are spam, delete them.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API called without checking its spec. |
| 2 | FNNNNPNF | Auth failed; API spec was not checked. |
| 3 | PPPNNPNP |  |
| 4 | PPPNNPNP |  |
| 5 | FNFNNFNF | Guessed password caused 401; no API spec. |
| 6 | PPPNNPNF | Supervisor API spec was not checked. |
| 7 | FNFNNPNF | Email username caused 401; spec unchecked. |
| 8 | PPPNNPNP |  |
| 9 | PNPNNPNP |  |
| 10 | PUPNNNNF | Returned records do not match; spec unchecked. |
| 11 | PUPNNFNF | Repeated identical query; spec still unchecked. |
| 12 | PUUNNFNF | Absence unproven; identical query repeated. |
| 13 | PUUNNFNF | Absence unproven; identical query repeated. |
| 14 | PUUNNFNF | Absence unproven; identical query repeated. |
| 15 | PUUNNFNF | Absence unproven; identical query repeated. |
| 16 | PUUNNFNF | Absence unproven; identical query repeated. |
| 17 | PUUNNFNF | Absence unproven; identical query repeated. |
| 18 | FNUNNPNF | Wrong parameter; contact absence unproven. |
| 19 | PUPNNPNF | Only first pages read; full specs unchecked. |
| 20 | PUPPPNNF | Coverage unknown; extra block, specs missing. |
| 21 | FNFNNNFF | No code ran; completion claim and protocol failed. |

### 82e2fac_1__04

 What is the title of the most-liked song in my Spotify playlists.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined variable caused NameError. |
| 2 | PPNNNPNF | No API spec checked for password lookup. |
| 3 | FNNNNPNP | Boolean value was indexed as a password entry. |
| 4 | PPPPNPNP |  |
| 5 | PNPNNNNP |  |
| 6 | PPNNNNNP |  |
| 7 | FNNPNNNF | show_song used without its API specification. |
| 8 | PPPPNPNF | show_song used without its API specification. |
| 9 | PNPNNNPF | complete_task used without its API spec. |

### aa8502b_3__00

 Follow all the artists who have sung at least one song I have liked on Spotify.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPPPNNNF | Supervisor API spec was not checked. |
| 3 | PNPNNNNP |  |
| 4 | PPNNNNNP |  |
| 5 | PPNNNNNP |  |
| 6 | PPPNNNNP |  |
| 7 | PPFPNNNF | Fabricated artist output; extra code block. |
| 8 | PPNNNNNP |  |
| 9 | PPNNNNNP |  |
| 10 | PPPPNNNP |  |
| 11 | FNNPNNNP | Duplicate follow caused a 422 exception. |
| 12 | FNFFNFNF | Follower count is not user follow status. |
| 13 | FFFFNFNF | Follow status was misread without API specs. |
| 14 | PPFNNFNP | Contradicts known API list; needless repeat. |
| 15 | FFFFNFNF | Repeated the same unverified status check. |
| 16 | FNFFNFNP | Repeated a known duplicate-follow failure. |
| 17 | FNNFNFNF | Errors were treated as not-following. |
| 18 | FNNPNFNP | Exception attributes were unsupported. |
| 19 | PPPPPPNP |  |
| 20 | PNPNNNPF | complete_task spec was not checked. |

### afc0fce_1__02

 Add a comment, "Thank you!", to all the venmo payments I received from my coworkers in the last 5 days (including today), and like those payments.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNFNNNF | Unknown API; date window spans six days. |
| 2 | PPNNNPNP |  |
| 3 | PPNNNPNP |  |
| 4 | FNNFNPNP | Token missing; date window spans six days. |
| 5 | FNNNNFNF | Password variable was undefined. |
| 6 | FNNNNFNP | Passwords variable was undefined. |
| 7 | PPNNNPNF | Supervisor API spec was not checked. |
| 8 | FNNNNPNP | Boolean value was indexed as a record. |
| 9 | PPPNNPNP |  |
| 10 | PNPNNPNF | Venmo login spec was not checked. |
| 11 | PUPFNPNF | Pagination incomplete; date range is wrong. |
| 12 | PUUFUNNF | Coworkers unverified; write specs unchecked. |
| 13 | FNFNNNFF | No code ran; completion was not submitted. |

### c901732_3__04

 Play the most listened to song on Spotify from the Velvet Underground album.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNF | Unknown API; no specification was checked. |
| 2 | PPNNNPNF | Credential API was used without its spec. |
| 3 | PPPPNNNP |  |
| 4 | PNPNNNNP |  |
| 5 | PFNNNNNP | Only the default playlist page was read. |
| 6 | FFFFNNNF | IDs were misread and playlist counts used. |
| 7 | FNPFNPNF | Unchecked API had an invalid parameter. |
| 8 | PPNNNPNP |  |
| 9 | FFFFNPNF | Playlist frequency was mistaken for plays. |
| 10 | PPNNNPNP |  |
| 11 | FNFFNPNF | Chosen song was unsupported; token omitted. |
| 12 | PPNNNPNP |  |
| 13 | PNFFUPNP | Wrong metric; correct target remains unknown. |
| 14 | PNUNNNUF | Completion claimed without target evidence. |

### ccb4494_1__05

 Like all the songs played so far in my spotify music player queue, including the current one.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | FNNNNNNF | Unauthorized call; API spec unchecked. |
| 3 | FNNNNPNF | Bad password extraction; API spec unchecked. |
| 4 | PPPNNPNF | Password API spec was not checked. |
| 5 | PNPNNNNP |  |
| 6 | PPPNNPNF | Queue API spec was not checked. |
| 7 | PPPFFNNF | Liked unplayed songs; API spec unchecked. |
| 8 | PNPNNNPF | Completion API spec was not checked. |

### ce359b5_3__04

 Remove all songs from my Spotify song library and playlists that were released in or before 2021 year.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPNNNNNP |  |
| 3 | FNNNNNNF | Undefined token; pagination was capped. |
| 4 | FNNFNFNP | Undefined passwords and malformed selection. |
| 5 | PPNNNPNF | Supervisor API spec was not checked. |
| 6 | FNNFNPNP | Boolean list item indexed as a record. |
| 7 | PPPPNPNP |  |
| 8 | PPNNNNNP |  |
| 9 | PFFFNNNP | Used added_at as the release year. |
| 10 | PPPFNNNP | Addition dates do not prove release years. |
| 11 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 12 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 13 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 14 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 15 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 16 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 17 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 18 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 19 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 20 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 21 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 22 | PFFFNFNP | Repeated page 10; release evidence absent. |
| 23 | PFFFNFNP | Repeated page 10; release evidence absent. |

### d0b1f43_1__05

 How much money have I sent to my roommates on venmo since 1st Jan of this year?

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNF | API specification was not checked. |
| 2 | PPPNNNNP |  |
| 3 | PNPNNNNF | API specification was not checked. |
| 4 | FNFFNNNF | Invented roommates and invalid API arguments. |
| 5 | FNFFNPNF | Invented roommates; date format was invalid. |
| 6 | PFFFNPNF | Uses invented roommates and omits pagination. |
| 7 | PFFPNNNP | Totals evidence for invented roommates. |
| 8 | PNFFNNFF | Unsupported total submitted without API docs. |

### e3d6c94_2__00

 Add all spotify-recommended R&B songs released in this or last year to a new "Spotify R&B Recommendations" playlist.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | FNNNNNNF | Call failed 401; API spec was not checked. |
| 3 | PPPNNFNP | Repeated the same query without new information. |
| 4 | PPPNNFNP | Repeated the same query without new information. |
| 5 | PPPNNFNP | Repeated the same query without new information. |
| 6 | PPFNNFNP | Login was visible; query was needlessly repeated. |
| 7 | PPFNNFNP | Login was visible; query was needlessly repeated. |
| 8 | PPFNNFNP | Login was visible; query was needlessly repeated. |
| 9 | PPFNNFNP | Login was visible; query was needlessly repeated. |
| 10 | PPFNNFNP | Login was visible; query was needlessly repeated. |
| 11 | PPFNNFNP | Login was visible; query was needlessly repeated. |
| 12 | PPFNNFNP | Login was visible; query was needlessly repeated. |
| 13 | PPFNNFNP | Login was visible; query was needlessly repeated. |

### e85d92a_1__05

 What is the title of the most played song by Velvet Echo on Spotify.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | PPNNNNNP |  |
| 2 | PPNNNNNP |  |
| 3 | PPNNNNNF | show_account_passwords spec not checked. |
| 4 | FNFNNNNP | Boolean result indexed as a password row. |
| 5 | PPPNNPNP |  |
| 6 | PPPNNNNF | search_songs spec not checked. |
| 7 | PUUUNNNP | Complete song coverage was not established. |
| 8 | PNUUNNUF | Coverage unknown; complete_task doc missing. |

### e85d92a_2__01

 What is the title of the least played song by Zoey James on Spotify.

| Step | R1–R8 | Reason |
|---:|---|---|
| 1 | FNNNNNNP | Undefined passwords caused NameError. |
| 2 | PPNNNPNF | Supervisor API spec was not checked. |
| 3 | FNNNNPNP | Boolean was indexed, causing TypeError. |
| 4 | PPPNNPNP |  |
| 5 | FNNNNNNF | Nonexistent, undocumented search API was called. |
| 6 | PPNNNPNP |  |
| 7 | FNNNNPNF | Called search_songs without checking its spec. |
| 8 | FNNNNFNF | Kept a parameter known to be unsupported. |
| 9 | PPNNNPNP |  |
| 10 | FNNNNPNF | page_limit=100 violated the documented maximum. |
| 11 | PPNNNPNP |  |
| 12 | PPPPNNNF | Commentary added a second nonempty code block. |
| 13 | PUPPNNNP | Unread pages may contain lower-play songs. |
| 14 | PUUNNNUF | Answer rests on an incomplete pagination check. |

