#ifndef LM_H_
#define LM_H_

#include "torch/script.h"
#include "torch/torch.h"

#include <memory>
#include <string>
#include <vector>

const char kSOS[] = "<s>";
const char kEOS[] = "</s>";

using TorchModule = torch::jit::script::Module;

class RNNLm {
public:
  void Read(const std::string &model_path, const int num_threads = 1);

  // Process given state with given label, return weight and the next state
  float Step(torch::Tensor& state, int prev_ilabel, int ilabel, torch::Tensor* next_state);

  float StepEos(torch::Tensor& state, int prev_ilabel, torch::Tensor* next_state);
  int start() const { return start_; }

private:
  std::shared_ptr<TorchModule> module_ = nullptr;
  // 100 for now it should be equal to sos/eos index int  dit index
  int sos_ = 99;
  int eos_ = 99;
  int start_ = 99;


  int prev_ids = -1;
};

#endif // LM_H
