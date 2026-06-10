class RecommendationModel:
    def predict(self, age, weight, height, activity_level_str, goal_str):
        # Rule-based recommendation engine — lightweight, no external dependencies
        # Produces plan IDs based on user profile inputs
        
        # Default fallback
        diet_plan_id = 2 # Balanced
        workout_plan_id = 2 # Strength
        
        # Simple logic based on goal
        if goal_str == 'loss':
            diet_plan_id = 1 # Low Carb
            workout_plan_id = 1 # Cardio/HIIT
        elif goal_str == 'gain':
            diet_plan_id = 3 # High Protein
            workout_plan_id = 2 # Strength
        
        # Adjust based on activity
        if activity_level_str in ['very_active', 'super_active'] and goal_str != 'loss':
            workout_plan_id = 3 # Complete Athlete
            
        return diet_plan_id, workout_plan_id

# Create a singleton instance
recommender = RecommendationModel()
