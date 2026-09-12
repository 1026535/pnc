# Shared outgoing request path

**Evidence:** client source verified for the [recorded packaged build](PROVENANCE.md); checksum offline checked. No live packets were captured or sent as validation.

## Bridge and dispatch

```text
Lua request wrapper
  -> LuaManager.SimpleInstrSend
  -> CopyLuaTableToObj
  -> AppFrame.SimpleInstrSend / Instruction
  -> AppFrame.SendInstruction (registered sender handler)
  -> SocketConnection.SendMsg
  -> SocketConnection.WriteToSocket
  -> SocketThread send queue
  -> Socket.Send
```

| Bridge argument | Observed role |
|---|---|
| `moduleId`, `cmd` | Signed 16-bit bridge arguments; become 32-bit destination/command fields |
| `data` | Lua table copied to a managed Hashtable; becomes server payload |
| `clientData` | Local context retained in SocketClientVO, indexed by request sequence |
| `showLoading` | Local SocketClientVO flag |
| `duration` | Local request tracking input |

The last three arguments are not serialized by the inspected packet writer. The request object receives a timestamp, but this writer does not put it on the wire. A registered sender handler runs before SendMsg and must be considered when tracing a particular request.

The outgoing path uses a custom TCP frame with UTF-8 JSON. It is not an HTTP endpoint. A method named `AppFrame.SendSocketInstruction` uses the receiver dictionary in the inspected code; it is not the outgoing hop above.

## Frame evidence

Let N be the JSON payload's byte count. Integers are big-endian in this ARM64 build.

| Offset | Bytes | Field |
|---|---|---|
| 0 | 4 | Magic `0x91201314` |
| 4 | 4 | Length `N + 21`, excluding the first 8 bytes |
| 8 | 4 | Checksum of the inner header plus payload |
| 12 | 4 | Request sequence |
| 16 | 4 | Destination |
| 20 | 4 | Command |
| 24 | 1 | Zero in the inspected writer; semantic meaning unconfirmed |
| 25 | 4 | N |
| 29 | N | UTF-8 JSON bytes |

No encryption/compression operation appears between this writer and its socket send loop. This is a finding about one code path, not a guarantee about all game traffic, authentication, or server acceptance. Null payload has a separate zero-length branch; empty-table conversion and precise JSON formatting require inspection when relevant.

The routine named `fnvHash` uses signed bytes, 32-bit overflow, and extra mixing; it is not interchangeable with standard unsigned FNV. With wrapping arithmetic: start at `0x811C9DC5`, XOR each sign-extended byte and multiply by `0x01000193`; then apply `h += h << 13`, `h ^= h >> 7`, `h += h << 3`, `h ^= h >> 17`, `h += h << 5`. Both right shifts are arithmetic. The reconstruction matched isolated native emulation for empty, ASCII, all-byte-values, and UTF-8 inputs. That check establishes checksum behavior, not a functioning client.

## Native source anchors

These are RVAs in the versioned `libil2cpp.so`, not live process addresses.

| Symbol | RVA |
|---|---|
| `LuaManager.SimpleInstrSend` | `0x17AC41C` |
| `LuaSamePropertyObjectUtil.CopyLuaTableToObj` | `0x17C5F50` |
| `AppFrame.SimpleInstrSend` | `0x1768694` |
| `Instruction` constructor | `0x1797D54` |
| `AppFrame.SendInstruction` | `0x17687D4` |
| `SocketConnection.SendMsg` | `0x17E149C` |
| `SocketConnection.WriteToSocket` | `0x17E167C` |
| `SocketStream.WriteInt` | `0x17E5124` |
| `HashAlgorithms.fnvHash` | `0x17C3B80` |
| `SocketThread.SenddThreadHandler` | `0x17E6370` |

Detailed local evidence: `.local-data/apk-exploration/native-trace/`, `SIMPLE_INSTR_TRACE.md`, and `il2cppdumper/script.json`. `dump.cs` supplies signatures/field offsets with empty method bodies; it is not implementation source.

## Validation implications

Follow the response handler and resulting state changes to identify meaningful success observations. Calling a wrapper, enqueueing a packet, or receiving any response does not prove the requested operation succeeded. Do not interpret a client-only loading option as a server requirement. Direct calls remain outside the reference's validation mechanism: authentication, receive framing, and server acceptance have not been established.
