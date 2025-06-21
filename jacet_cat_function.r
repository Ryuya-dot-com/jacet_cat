# JACET語彙サイズテスト CAT実装
# 3PLモデルを使用したComputer Adaptive Testing

library(ltm)
library(catR)
library(jsonlite)

# 3PLモデルの確率関数
prob_3pl <- function(theta, a, b, c) {
  return(c + (1 - c) / (1 + exp(-a * (theta - b))))
}

# 項目情報関数
item_info_3pl <- function(theta, a, b, c) {
  p <- prob_3pl(theta, a, b, c)
  q <- 1 - p
  info <- (a^2 * q * (p - c)^2) / (p * (1 - c)^2)
  return(info)
}

# テスト情報関数
test_info <- function(theta, administered_items, item_bank) {
  if(length(administered_items) == 0) return(0)
  
  total_info <- 0
  for(i in administered_items) {
    a <- item_bank$Dscrimination[i]
    b <- item_bank$Difficulty[i]
    c <- item_bank$Guessing[i]
    total_info <- total_info + item_info_3pl(theta, a, b, c)
  }
  return(total_info)
}

# CAT セッション初期化
init_cat_session <- function(item_bank, se_threshold = 0.4, max_items = 30, min_items = 5) {
  list(
    item_bank = item_bank,
    administered_items = c(),
    responses = c(),
    current_theta = 0,  # 初期能力値
    current_se = Inf,
    se_threshold = se_threshold,
    max_items = max_items,
    min_items = min_items,
    exposure_count = rep(0, nrow(item_bank))  # 項目露出制御
  )
}

# 次項目選択（最大情報量＋露出制御）
select_next_item <- function(session) {
  available_items <- setdiff(1:nrow(session$item_bank), session$administered_items)
  
  if(length(available_items) == 0) return(NULL)
  
  # 各利用可能項目の情報量を計算
  item_infos <- sapply(available_items, function(i) {
    a <- session$item_bank$Dscrimination[i]
    b <- session$item_bank$Difficulty[i]
    c <- session$item_bank$Guessing[i]
    return(item_info_3pl(session$current_theta, a, b, c))
  })
  
  # 露出制御: 過度に使用された項目にペナルティ
  max_exposure <- max(session$exposure_count)
  exposure_penalty <- session$exposure_count[available_items] / (max_exposure + 1)
  
  # 調整された情報量
  adjusted_infos <- item_infos * (1 - exposure_penalty * 0.3)
  
  # 最大情報量を持つ項目を選択
  selected_idx <- which.max(adjusted_infos)
  return(available_items[selected_idx])
}

# EAP（事後平均）による能力値推定
estimate_ability_eap <- function(session) {
  if(length(session$responses) == 0) {
    return(list(theta = 0, se = Inf))
  }
  
  # 事前分布: N(0, 1)
  theta_range <- seq(-4, 4, by = 0.01)
  prior <- dnorm(theta_range, 0, 1)
  
  # 尤度計算
  likelihood <- rep(1, length(theta_range))
  
  for(i in 1:length(session$administered_items)) {
    item_idx <- session$administered_items[i]
    response <- session$responses[i]
    
    a <- session$item_bank$Dscrimination[item_idx]
    b <- session$item_bank$Difficulty[item_idx]
    c <- session$item_bank$Guessing[item_idx]
    
    prob <- prob_3pl(theta_range, a, b, c)
    
    if(response == 1) {
      likelihood <- likelihood * prob
    } else {
      likelihood <- likelihood * (1 - prob)
    }
  }
  
  # 事後分布
  posterior <- likelihood * prior
  posterior <- posterior / sum(posterior)
  
  # EAP推定
  theta_eap <- sum(theta_range * posterior)
  
  # 事後標準偏差（SE）
  variance <- sum((theta_range - theta_eap)^2 * posterior)
  se <- sqrt(variance)
  
  return(list(theta = theta_eap, se = se))
}

# 回答処理
process_response <- function(session, item_id, response) {
  # 回答を記録
  session$administered_items <- c(session$administered_items, item_id)
  session$responses <- c(session$responses, response)
  session$exposure_count[item_id] <- session$exposure_count[item_id] + 1
  
  # 能力値更新
  ability_result <- estimate_ability_eap(session)
  session$current_theta <- ability_result$theta
  session$current_se <- ability_result$se
  
  return(session)
}

# 終了条件チェック
should_continue <- function(session) {
  # 最低項目数に達していない場合は継続
  if(length(session$administered_items) < session$min_items) {
    return(TRUE)
  }
  
  # 最大項目数に達した場合は終了
  if(length(session$administered_items) >= session$max_items) {
    return(FALSE)
  }
  
  # SE閾値による終了判定
  return(session$current_se > session$se_threshold)
}

# 語彙サイズ推定（JACET特有）
estimate_vocabulary_size <- function(theta) {
  # JACET 8000語リストに基づく語彙サイズ推定
  # レベル1-8のそれぞれ1000語に対応
  
  # 各レベルの平均困難度
  level_difficulties <- c(-2.206, -1.512, -0.701, -0.075, 0.748, 1.152, 1.504, 2.089)
  
  # 各レベルでの習得確率を計算（50%閾値）
  vocab_size <- 0
  for(i in 1:8) {
    prob_mastery <- 1 / (1 + exp(-(theta - level_difficulties[i])))
    vocab_size <- vocab_size + 1000 * prob_mastery
  }
  
  return(round(vocab_size))
}

# CATメイン実行関数
run_cat <- function(item_bank, se_threshold = 0.4, max_items = 30) {
  session <- init_cat_session(item_bank, se_threshold, max_items)
  
  while(should_continue(session)) {
    # 次項目選択
    next_item <- select_next_item(session)
    if(is.null(next_item)) break
    
    # ここで実際には受験者に問題を提示し、回答を取得
    # デモのため、ランダム回答をシミュレート
    cat(sprintf("項目 %d: %s (Level %d)\n", 
                next_item, 
                session$item_bank$Item[next_item],
                session$item_bank$Level[next_item]))
    
    # 実際の実装では、ここでWebインターフェースから回答を受け取る
    # response <- get_user_response(next_item)
    
    # デモ用ランダム回答（実際には削除）
    prob_correct <- prob_3pl(session$current_theta,
                           session$item_bank$Dscrimination[next_item],
                           session$item_bank$Difficulty[next_item],
                           session$item_bank$Guessing[next_item])
    response <- rbinom(1, 1, prob_correct)
    
    # 回答処理
    session <- process_response(session, next_item, response)
    
    cat(sprintf("能力値: %.3f (SE: %.3f)\n\n", session$current_theta, session$current_se))
  }
  
  # 最終結果
  vocab_size <- estimate_vocabulary_size(session$current_theta)
  
  result <- list(
    final_theta = session$current_theta,
    final_se = session$current_se,
    vocabulary_size = vocab_size,
    items_administered = length(session$administered_items),
    efficiency = length(session$administered_items) / 160  # 効率性
  )
  
  return(result)
}

# JSON出力用関数（PythonAnywhere連携）
cat_to_json <- function(session, next_item = NULL, final_result = NULL) {
  output <- list(
    current_theta = session$current_theta,
    current_se = session$current_se,
    items_count = length(session$administered_items),
    should_continue = should_continue(session)
  )
  
  if(!is.null(next_item)) {
    output$next_item <- list(
      id = next_item,
      word = session$item_bank$Item[next_item],
      level = session$item_bank$Level[next_item],
      correct_answer = session$item_bank$CorrectAnswer[next_item],
      distractors = list(
        session$item_bank$Distractor_1[next_item],
        session$item_bank$Distractor_2[next_item],
        session$item_bank$Distractor_3[next_item]
      )
    )
  }
  
  if(!is.null(final_result)) {
    output$final_result <- final_result
    output$vocabulary_size <- estimate_vocabulary_size(session$current_theta)
  }
  
  return(toJSON(output, auto_unbox = TRUE, pretty = TRUE))
}

# 使用例
# item_bank <- read.csv("jacet_parameters.csv")  # CSVファイルから読み込み
# result <- run_cat(item_bank)
# print(result)