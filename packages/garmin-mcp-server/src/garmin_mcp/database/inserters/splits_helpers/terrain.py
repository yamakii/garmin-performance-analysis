"""Terrain classification from elevation data."""


class TerrainClassifier:
    """Classify terrain type based on elevation changes."""

    @staticmethod
    def classify_terrain(elevation_gain: float, elevation_loss: float) -> str:
        """
        Classify terrain type based on elevation changes.

        Args:
            elevation_gain: Elevation gain in meters
            elevation_loss: Elevation loss in meters

        Returns:
            Terrain type classification
        """
        total_elevation_change = abs(elevation_gain) + abs(elevation_loss)

        if total_elevation_change < 5:
            return "平坦"
        elif total_elevation_change < 15:
            return "起伏"
        elif total_elevation_change < 30:
            return "丘陵"
        else:
            return "山岳"
