// WP7 Logger/Replay: 버스 ⇄ MCAP (DEC-011, PRP-LOG-001, REQ-LOG-001)
//
// - MCAP 채널은 Zenoh 키와 1:1이다. 채널 topic = 키
// - application/protobuf;<전체 이름> 인코딩은 schema(encoding "protobuf", 데이터 = FileDescriptorSet)를 단다
// - 원래 Zenoh 인코딩은 채널 메타데이터 "zenoh_encoding"에 둔다. 재생 시 그대로 발행한다
#pragma once

#include <cstdint>
#include <filesystem>
#include <functional>
#include <memory>
#include <stop_token>
#include <string>
#include <string_view>
#include <vector>

#include "swarm/api/bus.hpp"

namespace google::protobuf {
class Descriptor;
}

namespace swarm::logger {

inline constexpr std::string_view kEncodingMetaKey = "zenoh_encoding";

// 시각(ns). MCAP log_time은 기록기 수신 시각이다
using ClockNs = std::function<std::uint64_t()>;
std::uint64_t system_clock_ns();
std::uint64_t steady_clock_ns();

// IMP-LOG-002: 메시지 타입의 FileDescriptorSet(의존 파일 먼저) 직렬화
std::string file_descriptor_set(const google::protobuf::Descriptor* d);

// application/protobuf;<name> 이면 name, 아니면 빈 문자열
std::string_view protobuf_type_of(std::string_view encoding);

// swarm.v1 생성 코드가 정적 라이브러리에서 빠지지 않게 디스크립터를 등록한다
void ensure_swarm_descriptors();

struct RecorderOptions {
  std::string keyexpr = "**";
  ClockNs clock = system_clock_ns;
  // IMP-LOG-010: 쓰기 큐 상한. 둘 중 하나라도 넘으면 새 샘플을 버리고 dropped_count()에 센다
  std::size_t max_queue_messages = 100'000;
  std::size_t max_queue_bytes = 64u << 20;
  // IMP-LOG-011: MCAP 메시지 색인 기록 여부. 켜면 채널이 많을 때 writer가 색인을 쥐고 RSS가 부하에 비례해 는다
  bool message_index = false;
};

struct RecorderStats {
  std::uint64_t written = 0;        // MCAP에 쓴 메시지
  std::uint64_t dropped = 0;        // 큐 상한 초과로 버린 메시지
  std::size_t queue_messages = 0;   // 지금 큐 길이
  std::size_t queue_bytes = 0;
  std::size_t peak_queue_messages = 0;
  std::size_t peak_queue_bytes = 0;
};

// IMP-LOG-001: 버스 구독 → MCAP 기록. 콜백은 여러 스레드에서 와도 된다
// IMP-LOG-010: 콜백은 유한 큐에 넣기만 하고 쓰기 스레드가 MCAP에 쓴다 (배압 = 드롭 + 카운트)
class Recorder {
 public:
  Recorder(Bus& bus, const std::filesystem::path& path, RecorderOptions opts = {});
  ~Recorder();
  Recorder(const Recorder&) = delete;
  Recorder& operator=(const Recorder&) = delete;

  void close();  // 구독 해제 후 파일을 닫는다. 여러 번 불러도 된다
  std::uint64_t message_count() const;  // MCAP에 쓴 메시지 수
  std::uint64_t dropped_count() const;
  RecorderStats stats() const;
  std::size_t channel_count() const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

struct ReplayOptions {
  double rate = 1.0;  // 배속. 0 이하면 기다리지 않고 바로 발행한다
  std::string keyexpr = "**";
  ClockNs now = steady_clock_ns;
  std::function<void(std::uint64_t until_ns)> wait_until;  // 비우면 now 기준으로 잔다
};

struct ReplayStats {
  std::uint64_t messages = 0;
  std::uint64_t skipped = 0;          // keyexpr에 맞지 않은 메시지
  std::uint64_t log_span_ns = 0;      // 첫 메시지 ~ 마지막 메시지 log_time
  bool stopped = false;
};

// IMP-LOG-003: MCAP을 log_time 순서로 읽어 원래 간격 / rate 로 버스에 다시 발행한다
ReplayStats replay(Bus& bus, const std::filesystem::path& path, const ReplayOptions& opts = {},
                   std::stop_token stop = {});

struct ChannelInfo {
  std::string topic;
  std::string encoding;     // 재생 시 쓰는 Zenoh 인코딩
  std::string schema_name;  // 없으면 빈 문자열
  std::uint64_t messages = 0;
};

struct McapInfo {
  std::vector<ChannelInfo> channels;  // topic 순
  std::uint64_t messages = 0;
  std::uint64_t start_ns = 0;
  std::uint64_t end_ns = 0;
};

McapInfo inspect(const std::filesystem::path& path);

}  // namespace swarm::logger
