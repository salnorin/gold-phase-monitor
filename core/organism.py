self.generation = 1
    self.performance_history = []
    self.memory = []

def perceive_and_process(self) -> Optional[pd.DataFrame]:
    df = self.data_feeder.fetch()
    if df is None or df.empty:
        return None

    df = self.motor.calculate_motor_drive(df)
    df = self.optical.calculate_optical_field(df)
    df = self.immune.evaluate_toxicity_and_stress(df)
    df = self.respiration.calculate_breathing_and_signals(df)

    organ_results = self.morphogenesis.run_all_organs(df)
    for name, result in organ_results.items():
        if isinstance(result, dict):
            for col, values in result.items():
                df[col] = values

    return df

def think(self, latest_row: pd.Series) -> str:
    return BiologicalAIAnalyst.generate_diagnostic(latest_row)

def evaluate_performance(self, df: pd.DataFrame) -> float:
    if "Signal_Success" not in df.columns or "Signal_Attempted" not in df.columns:
        return 0.5

    recent = df[df["Signal_Attempted"] == 1].tail(20)
    if recent.empty:
        return 0.5

    win_rate = recent["Signal_Success"].mean()
    self.performance_history.append(float(win_rate))
    return float(win_rate)

def evolve_if_needed(self, win_rate: float) -> None:
    if len(self.performance_history) < 5:
        return

    recent_avg = sum(self.performance_history[-5:]) / 5

    if recent_avg < 0.40:
        self.generation += 1
        print(f"نسل {self.generation} | عملکرد اخیر: {recent_avg:.1%} → شروع تکامل")

        organ_code = '''
