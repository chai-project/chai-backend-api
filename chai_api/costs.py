from metno_locationforecast import Place, Forecast


def calculate_output_coefficient(temperature: float):
    """
    Calculate the output coefficient for a radiator given the boiler temperature.
    This coefficient is calculated for the default BTU values assuming ΔT = 50.
    In addition, as the hot water needs to move through pipework, a temperature drop of 5°C is assumed.
    :param temperature: The temperature of the boiler.
    """
    temperature -= 5  # assume a drop in temperature of 5°C before the water reaches the boiler
    return max(0, 0.000112378 * pow(temperature, 2) + 0.0143811 * temperature)


def estimate_heating_time(latitude: float, longitude: float, height: int,
                          temperature_room: float, volume_room: float, temperature_boiler: float,
                          temperature_delta: float, loss_factor_per_kelvin: float, heat_btu_at_50: float) -> float:
    """
    Estimate the time it takes to heat a room in minutes.
    :param latitude: The latitude of the room.
    :param longitude: The longitude of the room.
    :param height: The height of the room.
    :param temperature_room: The current temperature of the room.
    :param volume_room: The volume of the room in cubic metres.
    :param temperature_boiler: The temperature of the boiler.
    :param temperature_delta: The temperature difference between the current temperature and the desired temperature.
    :param loss_factor_per_kelvin: The loss factor per Kelvin for this property.
    :param heat_btu_at_50: The BTU value of the radiator at a temperature difference of 50°C.
    """
    temperature_avg_during_heating = temperature_room + temperature_delta / 2
    temperature_delta_t = max(0.0, temperature_boiler - temperature_avg_during_heating)
    kwh_in = heat_btu_at_50 * calculate_output_coefficient(temperature_delta_t) / 3.41 / 1_000

    home = Place("Home", latitude, longitude, height)
    forecast = Forecast(home, "chai-research-api/1.0")
    forecast.update()  # get a 9-day forecast

    outside_temperature = 10
    kwh_out = loss_factor_per_kelvin * (temperature_avg_during_heating - outside_temperature) / 1_000
    print(kwh_in, kwh_out)

    if abs(kwh_in - kwh_out) < 0.01:
        return 1440

    return min(1440.0, volume_room * temperature_delta / (4.96 * (kwh_in - kwh_out)))


if __name__ == "__main__":
    print(estimate_heating_time(56.025570, -3.814310, 20,
                                temperature_room=15, volume_room=40, temperature_boiler=65,
                                temperature_delta=-7, loss_factor_per_kelvin=80, heat_btu_at_50=0))
