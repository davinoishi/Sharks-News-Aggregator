#!/usr/bin/env python3
"""
Seed initial entities (Sharks roster) into the database.

This script adds common Sharks players, coaches, and team entities.
Update the lists below with current roster as needed.

Usage:
    python -m app.scripts.seed_entities
"""
from app.core.database import SessionLocal
from app.core.db_utils import get_or_create_entity


# Current Sharks roster (2025-26 season)
# Update this list as roster changes
PLAYERS = [
    "Macklin Celebrini",
    "Will Smith",
    "Mikael Granlund",
    "Tyler Toffoli",
    "Fabian Zetterlund",
    "Alexander Wennberg",
    "Nico Sturm",
    "Luke Kunin",
    "Klim Kostin",
    "Barclay Goodrow",
    "Carl Grundstrom",
    "Ty Dellandrea",
    "Ethan Cardwell",
    "Givani Smith",
    "Mackenzie Blackwood",
    "Vitek Vanecek",
    "Yaroslav Askarov",
    "Jake Walman",
    "Mario Ferraro",
    "Cody Ceci",
    "Jan Rutta",
    "Henry Thrun",
    "Matt Benning",
    "Jack Thompson",
    "Shakir Mukhamadullin",
    # Add more players as needed
]

COACHES = [
    "Ryan Warsofsky",  # Head Coach
    "Brian Wiseman",   # Assistant Coach
    "Doug Houda",      # Assistant Coach
    "Thomas Speer",    # Goaltending Coach
    # Add more coaching staff as needed
]

TEAMS = [
    "San Jose Sharks",
    "San Jose Barracuda",  # AHL affiliate
]

PROSPECTS = [
    "Quentin Musty",
    "Sam Dickinson",
    "Kasper Halttunen",
    # Add more prospects as needed
]


def seed_entities(dry_run: bool = False) -> dict:
    """
    Seed entities into the database.

    Args:
        dry_run: If True, print what would be created without saving

    Returns:
        Dictionary with counts of entities created
    """
    db = SessionLocal()
    counts = {
        'players': 0,
        'coaches': 0,
        'teams': 0,
        'prospects': 0,
    }

    try:
        print("Seeding entities...")
        if dry_run:
            print("(DRY RUN - no changes will be saved)\n")

        # Seed players
        print(f"Adding {len(PLAYERS)} players...")
        for player_name in PLAYERS:
            if dry_run:
                print(f"  Would create player: {player_name}")
                counts['players'] += 1
            else:
                entity = get_or_create_entity(
                    db,
                    name=player_name,
                    entity_type='player',
                    extra_metadata={'status': 'active'}
                )
                print(f"  ✓ {player_name} (ID: {entity.id}, slug: {entity.slug})")
                counts['players'] += 1

        # Seed coaches
        print(f"\nAdding {len(COACHES)} coaches...")
        for coach_name in COACHES:
            if dry_run:
                print(f"  Would create coach: {coach_name}")
                counts['coaches'] += 1
            else:
                entity = get_or_create_entity(
                    db,
                    name=coach_name,
                    entity_type='coach',
                    extra_metadata={'status': 'active'}
                )
                print(f"  ✓ {coach_name} (ID: {entity.id}, slug: {entity.slug})")
                counts['coaches'] += 1

        # Seed teams
        print(f"\nAdding {len(TEAMS)} teams...")
        for team_name in TEAMS:
            if dry_run:
                print(f"  Would create team: {team_name}")
                counts['teams'] += 1
            else:
                entity = get_or_create_entity(
                    db,
                    name=team_name,
                    entity_type='team',
                    extra_metadata={}
                )
                print(f"  ✓ {team_name} (ID: {entity.id}, slug: {entity.slug})")
                counts['teams'] += 1

        # Seed prospects
        print(f"\nAdding {len(PROSPECTS)} prospects...")
        for prospect_name in PROSPECTS:
            if dry_run:
                print(f"  Would create prospect: {prospect_name}")
                counts['prospects'] += 1
            else:
                entity = get_or_create_entity(
                    db,
                    name=prospect_name,
                    entity_type='player',
                    extra_metadata={'status': 'prospect'}
                )
                print(f"  ✓ {prospect_name} (ID: {entity.id}, slug: {entity.slug})")
                counts['prospects'] += 1

        if not dry_run:
            db.commit()

        return counts

    except Exception as e:
        db.rollback()
        print(f"\n✗ Error during seeding: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    import sys

    dry_run = '--dry-run' in sys.argv

    try:
        counts = seed_entities(dry_run=dry_run)

        print("\n" + "="*60)
        print("Summary:")
        print(f"  Players: {counts['players']}")
        print(f"  Coaches: {counts['coaches']}")
        print(f"  Teams: {counts['teams']}")
        print(f"  Prospects: {counts['prospects']}")
        print(f"  Total: {sum(counts.values())}")

        if not dry_run:
            print("\n✓ Entities successfully seeded!")
            print("\nVerify entities:")
            print("  docker-compose exec db psql -U sharks -d sharks -c 'SELECT id, name, entity_type FROM entities LIMIT 10;'")
        else:
            print("\nDry run complete. Use without --dry-run to save changes.")

        print("="*60)

    except Exception as e:
        print(f"\n✗ Failed to seed entities: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
