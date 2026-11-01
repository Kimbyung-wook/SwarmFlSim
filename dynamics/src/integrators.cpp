// IMP-DYN-003, IMP-DYN-004 (REQ-DYN-003, REQ-DYN-004, DEC-005)
#include "swarm/dyn/integrators.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace swarm::dyn {
namespace {

void ensure(std::vector<double>& v, std::size_t n) {
  if (v.size() != n) v.assign(n, 0.0);
}

void copy(std::span<const double> from, std::span<double> to) { std::copy(from.begin(), from.end(), to.begin()); }

// [ts, ts+h] 안에서 g의 부호가 바뀐 경우 교차 시점을 이분 탐색한다.
// single(τ, xs → out)은 ts에서 τ만큼 한 스텝 적분한다. x_out에는 교차 직후(g가 넘어간 쪽) 상태를 쓴다.
// 반환값은 이벤트 시각(교차 직후 쪽 구간 끝).
template <class Single>
double bisect_event(const EventFn& g, double ts, double h, double gs, std::span<double> x_out,
                    std::vector<double>& scratch, double tol, Single&& single) {
  ensure(scratch, x_out.size());
  double lo = 0.0, hi = h;
  for (int i = 0; i < 200 && hi - lo > tol; ++i) {
    const double mid = 0.5 * (lo + hi);
    single(mid, std::span<double>(scratch));
    if (crossed(gs, g(ts + mid, scratch))) {
      hi = mid;
      copy(scratch, x_out);
    } else {
      lo = mid;
    }
  }
  return ts + hi;
}

bool reached(double t, double t_end) { return t_end - t <= 1e-12 * std::max(1.0, std::abs(t_end)); }

}  // namespace

// ---------------------------------------------------------------- RK4

void Rk4Integrator::single(const DynamicsModel& model, double t, double h, std::span<const double> x0,
                           std::span<double> x1, std::span<const double> u, const Environment& env) {
  const std::size_t n = x0.size();
  model.derivatives(t, x0, u, env, k1_);
  for (std::size_t i = 0; i < n; ++i) tmp_[i] = x0[i] + 0.5 * h * k1_[i];
  model.derivatives(t + 0.5 * h, tmp_, u, env, k2_);
  for (std::size_t i = 0; i < n; ++i) tmp_[i] = x0[i] + 0.5 * h * k2_[i];
  model.derivatives(t + 0.5 * h, tmp_, u, env, k3_);
  for (std::size_t i = 0; i < n; ++i) tmp_[i] = x0[i] + h * k3_[i];
  model.derivatives(t + h, tmp_, u, env, k4_);
  for (std::size_t i = 0; i < n; ++i) x1[i] = x0[i] + h / 6.0 * (k1_[i] + 2.0 * k2_[i] + 2.0 * k3_[i] + k4_[i]);
}

StepResult Rk4Integrator::step(const DynamicsModel& model, double t0, double dt, std::span<double> x,
                               std::span<const double> u, const Environment& env, const EventFn* event) {
  const std::size_t n = x.size();
  for (auto* v : {&k1_, &k2_, &k3_, &k4_, &tmp_, &xn_}) ensure(*v, n);

  int count = 1;
  if (cfg_.max_step_s > 0.0) count = std::max(1, static_cast<int>(std::ceil(dt / cfg_.max_step_s - 1e-9)));
  const double h = dt / count;

  StepResult r;
  double t = t0;
  double gs = event ? (*event)(t0, x) : 0.0;
  for (int s = 0; s < count; ++s) {
    single(model, t, h, x, xn_, u, env);
    ++r.substeps;
    if (event) {
      const double g1 = (*event)(t + h, xn_);
      if (crossed(gs, g1)) {
        std::vector<double> xs(x.begin(), x.end());
        const double ts = t;
        r.t_end = bisect_event(*event, ts, h, gs, xn_, xb_, cfg_.event_time_tol_s,
                               [&](double tau, std::span<double> out) { single(model, ts, tau, xs, out, u, env); });
        copy(xn_, x);
        r.event = true;
        return r;
      }
      gs = g1;
    }
    copy(xn_, x);
    t = (s + 1 == count) ? t0 + dt : t + h;
  }
  r.t_end = t0 + dt;
  return r;
}

// ---------------------------------------------------------------- RK45 (Dormand-Prince 5(4))

namespace {
constexpr double kA21 = 1.0 / 5;
constexpr double kA31 = 3.0 / 40, kA32 = 9.0 / 40;
constexpr double kA41 = 44.0 / 45, kA42 = -56.0 / 15, kA43 = 32.0 / 9;
constexpr double kA51 = 19372.0 / 6561, kA52 = -25360.0 / 2187, kA53 = 64448.0 / 6561, kA54 = -212.0 / 729;
constexpr double kA61 = 9017.0 / 3168, kA62 = -355.0 / 33, kA63 = 46732.0 / 5247, kA64 = 49.0 / 176,
                 kA65 = -5103.0 / 18656;
constexpr double kB1 = 35.0 / 384, kB3 = 500.0 / 1113, kB4 = 125.0 / 192, kB5 = -2187.0 / 6784, kB6 = 11.0 / 84;
// 5차 − 4차 가중치
constexpr double kE1 = 71.0 / 57600, kE3 = -71.0 / 16695, kE4 = 71.0 / 1920, kE5 = -17253.0 / 339200,
                 kE6 = 22.0 / 525, kE7 = -1.0 / 40;
constexpr double kC2 = 1.0 / 5, kC3 = 3.0 / 10, kC4 = 4.0 / 5, kC5 = 8.0 / 9;
}  // namespace

double Rk45Integrator::attempt(const DynamicsModel& model, double t, double h, std::span<const double> x0,
                               std::span<double> x1, std::span<const double> u, const Environment& env,
                               bool want_error) {
  const std::size_t n = x0.size();
  auto& k1 = k_[0];
  auto& k2 = k_[1];
  auto& k3 = k_[2];
  auto& k4 = k_[3];
  auto& k5 = k_[4];
  auto& k6 = k_[5];
  auto& k7 = k_[6];

  model.derivatives(t, x0, u, env, k1);
  for (std::size_t i = 0; i < n; ++i) tmp_[i] = x0[i] + h * kA21 * k1[i];
  model.derivatives(t + kC2 * h, tmp_, u, env, k2);
  for (std::size_t i = 0; i < n; ++i) tmp_[i] = x0[i] + h * (kA31 * k1[i] + kA32 * k2[i]);
  model.derivatives(t + kC3 * h, tmp_, u, env, k3);
  for (std::size_t i = 0; i < n; ++i) tmp_[i] = x0[i] + h * (kA41 * k1[i] + kA42 * k2[i] + kA43 * k3[i]);
  model.derivatives(t + kC4 * h, tmp_, u, env, k4);
  for (std::size_t i = 0; i < n; ++i)
    tmp_[i] = x0[i] + h * (kA51 * k1[i] + kA52 * k2[i] + kA53 * k3[i] + kA54 * k4[i]);
  model.derivatives(t + kC5 * h, tmp_, u, env, k5);
  for (std::size_t i = 0; i < n; ++i)
    tmp_[i] = x0[i] + h * (kA61 * k1[i] + kA62 * k2[i] + kA63 * k3[i] + kA64 * k4[i] + kA65 * k5[i]);
  model.derivatives(t + h, tmp_, u, env, k6);
  for (std::size_t i = 0; i < n; ++i)
    x1[i] = x0[i] + h * (kB1 * k1[i] + kB3 * k3[i] + kB4 * k4[i] + kB5 * k5[i] + kB6 * k6[i]);
  if (!want_error) return 0.0;

  model.derivatives(t + h, x1, u, env, k7);
  double err = 0.0;
  for (std::size_t i = 0; i < n; ++i) {
    const double e = h * (kE1 * k1[i] + kE3 * k3[i] + kE4 * k4[i] + kE5 * k5[i] + kE6 * k6[i] + kE7 * k7[i]);
    const double sc =
        cfg_.atol * abs_scale_[i] + cfg_.rtol * rel_scale_[i] * std::max(std::abs(x0[i]), std::abs(x1[i]));
    if (sc > 0.0) err = std::max(err, std::abs(e) / sc);
  }
  return err;
}

StepResult Rk45Integrator::step(const DynamicsModel& model, double t0, double dt, std::span<double> x,
                                std::span<const double> u, const Environment& env, const EventFn* event) {
  const std::size_t n = x.size();
  for (auto& k : k_) ensure(k, n);
  for (auto* v : {&tmp_, &xn_}) ensure(*v, n);
  abs_scale_.assign(n, 1.0);
  rel_scale_.assign(n, 1.0);
  if (const auto* p = dynamic_cast<const ErrorScaleProvider*>(&model)) p->error_scale(abs_scale_, rel_scale_);

  StepResult r;
  const double t_end = t0 + dt;
  const double h_max = cfg_.max_step_s > 0.0 ? std::min(cfg_.max_step_s, dt) : dt;
  double h = h_max;
  double t = t0;
  double gs = event ? (*event)(t0, x) : 0.0;
  int tries = 0;

  while (!reached(t, t_end)) {
    if (++tries > cfg_.max_substeps) throw std::runtime_error("rk45: max_substeps exceeded");
    h = std::min(h, t_end - t);
    const bool last = h >= t_end - t;
    const double err = attempt(model, t, h, x, xn_, u, env, true);

    if (err > 1.0 && h > cfg_.min_step_s) {
      h = std::max(cfg_.min_step_s, h * std::max(0.2, 0.9 * std::pow(err, -0.2)));
      continue;
    }

    ++r.substeps;
    r.max_error = std::max(r.max_error, err);
    const double t_next = last ? t_end : t + h;
    if (event) {
      const double g1 = (*event)(t_next, xn_);
      if (crossed(gs, g1)) {
        std::vector<double> xs(x.begin(), x.end());
        const double ts = t;
        r.t_end = bisect_event(*event, ts, t_next - ts, gs, xn_, xb_, cfg_.event_time_tol_s,
                               [&](double tau, std::span<double> out) {
                                 attempt(model, ts, tau, xs, out, u, env, false);
                               });
        copy(xn_, x);
        r.event = true;
        return r;
      }
      gs = g1;
    }
    copy(xn_, x);
    t = t_next;
    const double grow = err > 0.0 ? 0.9 * std::pow(err, -0.2) : 5.0;
    h = std::min(h_max, h * std::clamp(grow, 0.2, 5.0));
  }
  r.t_end = t_end;
  return r;
}

}  // namespace swarm::dyn
