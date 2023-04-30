from typing import Optional


class StreamingStats:
    def __init__(self):
        self.current_average = 0
        self.num_observations = 0

    def update(self, new_observation: float):
        # Update the previous average
        previous_average = self.current_average
        previous_observations = self.num_observations
        new_num_observations = previous_observations + 1
        update_weight = previous_observations/new_num_observations
        self.current_average = previous_average*update_weight + new_observation/new_num_observations
        self.num_observations = new_num_observations

    @property
    def mean(self) -> Optional[float]:
        if self.num_observations <= 0:
            return None
        else:
            return self.current_average

    @property
    def report(self) -> str:
        if self.mean is None:
            formatted_mean = 'None'
        else:
            formatted_mean = f'{self.mean:.3f}'
        return f'Mean: {formatted_mean} || Observations: {self.num_observations}'
